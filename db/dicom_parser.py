#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse DICOM RT Dose, Structure, and Plan files for DVH Analytics SQL Database for DVHA > 0.6
This version of dicom_parser is longer, but hopefully easier to understand
Note that this version depends is designed for DVH_SQL().insert_row as opposed to
insert_plan, insert_beams, insert_rxs, insert_dvhs
Created on Sun Mar 17
@author: Dan Cutright, PhD
"""

from dicompylercore import dicomparser, dvhcalc
from dateutil.relativedelta import relativedelta  # python-dateutil
import numpy as np
import pydicom as dicom
from tools.roi_name_manager import DatabaseROIs, clean_name
from tools.utilities import datetime_str_to_obj, change_angle_origin, date_str_to_obj, calc_stats
from tools.roi_formatter import dicompyler_roi_coord_to_db_string, get_planes_from_string
from tools import roi_geometry as roi_calc
from tools.mlc_analyzer import Beam as mlca


class DICOM_Parser:
    def __init__(self, plan=None, structure=None, dose=None):

        self.plan_file = plan
        self.structure_file = structure
        self.dose_file = dose

        self.rt_data = {key: None for key in ['plan', 'structure', 'dose']}
        self.dicompyler_data = {key: None for key in ['plan', 'structure', 'dose']}
        if plan:
            self.rt_data['plan'] = dicom.read_file(plan)
            self.dicompyler_data['plan'] = dicomparser.DicomParser(plan)
            self.dicompyler_rt_plan = self.dicompyler_data['plan'].GetPlan()
        if structure:
            self.rt_data['structure'] = dicom.read_file(structure)
            self.dicompyler_data['structure'] = dicomparser.DicomParser(structure)
            self.dicompyler_rt_structures = self.dicompyler_data['structure'].GetStructures()
        if dose:
            self.rt_data['dose'] = dicom.read_file(dose)
            self.dicompyler_data['dose'] = dicomparser.DicomParser(dose)

        self.database_rois = DatabaseROIs()

        self.rx_data = []
        self.beam_data = {}
        for i, fx_grp in enumerate(self.rt_data['plan'].FractionGroupSequence):
            self.rx_data.append(RxParser(self.rt_data['plan'],
                                         self.dicompyler_rt_plan,
                                         self.rt_data['structure'], i))
            self.beam_data[i] = []
            for j, beam in enumerate(self.beam_sequence):
                self.beam_data[i].append(BeamParser(self.rt_data['plan'], i, j))

        # these properties are not inherently stored in DICOM
        self.non_dicom_properties = {'Plans': ['baseline', 'protocol', 'toxicity_grades'],
                                     'DVHs': ['dist_to_ptv_min', 'dist_to_ptv_mean', 'dist_to_ptv_median',
                                              'dist_to_ptv_max', 'ptv_overlap', 'dist_to_ptv_centroids', 'dth_string',
                                              'toxicity_grade'],
                                     'Rxs': ['rx_percent'],
                                     'Beams': []}

        # These properties are not inherently stored in Pinnacle DICOM files, but can be extracted from dummy ROI
        # names automatically generated by the Pinnacle Script provided by DVH Analytics
        self.pinnacle_properties = []

    def get_rx_data_from_dummy_rois(self):

        struct_seq = self.rt_data['structure'].StructureSetROISequence
        rx_indices = [i for i, roi in enumerate(struct_seq) if roi.ROIName.lower().startswith('rx ')]

        rx_data = {}
        for i in rx_indices:
            roi_name = struct_seq[i].ROIName.lower()
            name_split = roi_name.split(':')
            fx_grp_number = int(name_split[0].strip('rx '))
            fx_grp_name = name_split[1].strip()
            fx_dose = float(name_split[2].split('cgy')[0]) / 100.
            fxs = int(name_split[2].split('x ')[1].split(' to')[0])
            rx_dose = fx_dose * float(fxs)
            rx_percent = float(name_split[2].strip().split(' ')[5].strip('%'))
            normalization_method = name_split[3].strip()
            normalization_object = ['plan_max', name_split[4].strip()][normalization_method != 'plan_max']

            rx_data[fx_grp_number] = {'fx_grp_number': fx_grp_number,
                                      'fx_grp_name': fx_grp_name,
                                      'fx_dose': fx_dose,
                                      'fx_count': fxs,
                                      'rx_dose': rx_dose,
                                      'rx_percent': rx_percent,
                                      'normalization_method': normalization_method,
                                      'normalization_object': normalization_object}

        return rx_data

    def get_plan_row(self):

        return {'mrn': [self.mrn, 'text'],
                'study_instance_uid': [self.study_instance_uid, 'text'],
                'birth_date': [self.birth_date, 'date'],
                'age': [self.age, 'smallint'],
                'patient_sex': [self.patient_sex, 'char(1)'],
                'sim_study_date': [self.sim_study_date, 'date'],
                'physician': [self.physician, 'varchar(50)'],
                'tx_site': [self.tx_site, 'varchar(50)'],
                'rx_dose': [self.rx_dose, 'real'],
                'fxs': [self.fxs, 'int'],
                'patient_orientation': [self.patient_orientation, 'varchar(3)'],
                'plan_time_stamp': [self.plan_time_stamp, 'timestamp'],
                'struct_time_stamp': [self.struct_time_stamp, 'timestamp'],
                'dose_time_stamp': [self.dose_time_stamp, 'timestamp'],
                'tps_manufacturer': [self.tps_manufacturer, 'varchar(50)'],
                'tps_software_name': [self.tps_software_name, 'varchar(50)'],
                'tps_software_version': [self.tps_software_version, 'varchar(30)'],
                'tx_modality': [self.tx_modality, 'varchar(30)'],
                'tx_time': [self.tx_time, 'time'],
                'total_mu': [self.total_mu, 'real'],
                'dose_grid_res': [self.dose_grid_res, 'varchar(16)'],
                'heterogeneity_correction': [self.heterogeneity_correction, ' varchar(30)'],
                'baseline': [None, 'boolean'],
                'import_time_stamp': [None, 'timestamp'],
                'protocol': [None, 'text'],
                'toxicity_grades': [None, 'text']}

    def get_beam_rows(self):
        beam_rows = []
        for rx_index, beam_set in self.beam_data.items():
            for beam in beam_set:
                beam_rows.append(self.get_beam_row(rx_index, beam))
        return beam_rows

    def get_beam_row(self, rx_index, beam):
        rx = self.rx_data[rx_index]

        # store these getters so code is repeated every reference
        gantry_values = beam.gantry_values
        collimator_values = beam.collimator_value
        couch_values = beam.couch_values
        mlc_stat_data = beam.mlc_stat_data

        return {'mrn': [self.mrn, 'text'],
                'study_instance_uid': [self.study_instance_uid, 'text'],
                'beam_number': [beam.beam_number, 'int'],
                'beam_name': [beam.beam_name, 'varchar(30)'],
                'fx_grp_number': [rx.fx_grp_number, 'smallint'],
                'fx_count': [rx.fx_count, 'int'],
                'fx_grp_beam_count': [rx.beam_count, 'smallint'],
                'beam_dose': [beam.beam_dose, 'real'],
                'beam_mu': [beam.beam_mu, 'real'],
                'radiation_type': [beam.radiation_type, 'varchar(30)'],
                'beam_energy_min': [beam.energy_min, 'real'],
                'beam_energy_max': [beam.energy_max, 'real'],
                'beam_type': [beam.beam_type, 'varchar(30)'],
                'control_point_count': [beam.control_point_count, 'int'],
                'gantry_start': [gantry_values['start'], 'real'],
                'gantry_end': [gantry_values['end'], 'real'],
                'gantry_rot_dir': [gantry_values['rot_dir'], 'varchar(5)'],
                'gantry_range': [gantry_values['range'], 'real'],
                'gantry_min': [gantry_values['min'], 'real'],
                'gantry_max': [gantry_values['max'], 'real'],
                'collimator_start': [collimator_values['start'], 'real'],
                'collimator_end': [collimator_values['end'], 'real'],
                'collimator_rot_dir': [collimator_values['rot_dir'], 'varchar(5)'],
                'collimator_range': [collimator_values['range'], 'real'],
                'collimator_min': [collimator_values['min'], 'real'],
                'collimator_max': [collimator_values['max'], 'real'],
                'couch_start': [couch_values['start'], 'real'],
                'couch_end': [couch_values['end'], 'real'],
                'couch_rot_dir': [couch_values['rot_dir'], 'varchar(5)'],
                'couch_range': [couch_values['range'], 'real'],
                'couch_min': [couch_values['min'], 'real'],
                'couch_max': [couch_values['max'], 'real'],
                'beam_dose_pt': [beam.beam_dose_pt, 'varchar(35)'],
                'isocenter': [beam.isocenter, 'varchar(35)'],
                'ssd': [beam.ssd, 'real'],
                'treatment_machine': [beam.treatment_machine, 'varchar(30)'],
                'scan_mode': [beam.scan_mode, 'varchar(30)'],
                'scan_spot_count': [beam.scan_spot_count, 'real'],
                'beam_mu_per_deg': [beam.beam_mu_per_deg, 'real'],
                'beam_mu_per_cp': [beam.beam_mu_per_cp, 'real'],
                'import_time_stamp': [None, 'timestamp'],
                'area_min': [mlc_stat_data['area'][5], 'real'],
                'area_mean': [mlc_stat_data['area'][3], 'real'],
                'area_median': [mlc_stat_data['area'][2], 'real'],
                'area_max': [mlc_stat_data['area'][0], 'real'],
                'x_perim_min': [mlc_stat_data['x_perim'][5], 'real'],
                'x_perim_mean': [mlc_stat_data['x_perim'][3], 'real'],
                'x_perim_median': [mlc_stat_data['x_perim'][2], 'real'],
                'x_perim_max': [mlc_stat_data['x_perim'][0], 'real'],
                'y_perim_min': [mlc_stat_data['y_perim'][5], 'real'],
                'y_perim_mean': [mlc_stat_data['y_perim'][3], 'real'],
                'y_perim_median': [mlc_stat_data['y_perim'][2], 'real'],
                'y_perim_max': [mlc_stat_data['y_perim'][0], 'real'],
                'complexity_min': [mlc_stat_data['cmp_score'][5], 'real'],
                'complexity_mean': [mlc_stat_data['cmp_score'][3], 'real'],
                'complexity_median': [mlc_stat_data['cmp_score'][2], 'real'],
                'complexity_max': [mlc_stat_data['cmp_score'][0], 'real'],
                'cp_mu_min': [mlc_stat_data['cp_mu'][5], 'real'],
                'cp_mu_mean': [mlc_stat_data['cp_mu'][3], 'real'],
                'cp_mu_median': [mlc_stat_data['cp_mu'][2], 'real'],
                'cp_mu_max': [mlc_stat_data['cp_mu'][0], 'real'],
                'complexity': [mlc_stat_data['complexity'], 'real'],
                'tx_modality': [beam.tx_modality]}

    def get_rx_rows(self):
        return [self.get_rx_row(rx) for rx in self.rx_data]

    def get_rx_row(self, rx_index):
        rx = self.rx_data[rx_index]

        return {'mrn': [self.mrn, 'text'],
                'study_instance_uid': [self.study_instance_uid, 'text'],
                'plan_name': [rx.plan_name, 'varchar(50)'],
                'fx_grp_name': [rx.fx_grp_name, 'varchar(30)'],
                'fx_grp_number': [rx.fx_grp_number, 'smallint'],
                'fx_grp_count': [self.fx_grp_count, 'smallint'],
                'fx_dose': [rx.fx_dose, 'real'],
                'fxs': [rx.fx_count, 'smallint'],
                'rx_dose': [rx.rx_dose, 'real'],
                'rx_percent': [None, 'real'],
                'normalization_method': [rx.normalization_method, 'varchar(30)'],
                'normalization_object': [rx.normalization_object, 'varchar(30)'],
                'import_time_stamp': [None, 'timestamp']}

    def get_dvh_row(self, dvh_index):

        dvh = dvhcalc.get_dvh(self.structure_file, self.dose_file, dvh_index)
        geometries = self.get_dvh_geometries(dvh_index)

        return {'mrn': [self.mrn, 'text'],
                'study_instance_uid': [self.study_instance_uid, 'text'],
                'institutional_roi': [self.get_institutional_roi(dvh_index), 'varchar(50)'],
                'physician_roi': [self.get_physician_roi(dvh_index), 'varchar(50)'],
                'roi_name': [self.get_roi_name(dvh_index), 'varchar(50)'],
                'roi_type': [self.get_roi_type(dvh_index), 'varchar(20)'],
                'volume': [dvh.volume, 'real'],
                'min_dose': [dvh.min, 'real'],
                'mean_dose': [dvh.mean, 'real'],
                'max_dose': [dvh.max, 'real'],
                'dvh_string': [','.join(['%.2f' % num for num in dvh.counts]), 'text'],
                'roi_coord_string': [geometries['roi_coord_str'], 'text'],
                'dist_to_ptv_min': [None, 'real'],
                'dist_to_ptv_mean': [None, 'real'],
                'dist_to_ptv_median': [None, 'real'],
                'dist_to_ptv_max': [None, 'real'],
                'surface_area': [geometries['surface_area'], 'real'],
                'ptv_overlap': [None, 'real'],
                'import_time_stamp': [None, 'timestamp'],
                'centroid': [geometries['centroid'], 'varchar(35'],
                'dist_to_ptv_centroids': [None, 'real'],
                'dth_string': [None, 'text'],
                'spread_x': [geometries['spread'][0], 'real'],
                'spread_y': [geometries['spread'][1], 'real'],
                'spread_z': [geometries['spread'][2], 'real'],
                'cross_section_max': [geometries['cross_sections']['max'], 'real'],
                'cross_section_median': [geometries['cross_sections']['median'], 'real'],
                'toxicity_grade': [None, 'smallint']}

    @property
    def mrn(self):
        return self.rt_data['plan'].PatientID

    @property
    def study_instance_uid(self):
        return self.rt_data['plan'].StudyInstanceUID

    # ------------------------------------------------------------------------------
    # Plan table data
    # ------------------------------------------------------------------------------
    @property
    def tx_modality(self):
        tx_modalities = []
        for beams in self.beam_data.values():
            for beam in beams:
                tx_modalities.append(beam.tx_modality)
        return ','.join(list(set(tx_modalities)))

    @property
    def rx_dose(self):
        return sum([rx.rx_dose for rx in self.rx_data if rx.rx_dose])

    @property
    def total_mu(self):
        mus = []
        for i, beamset in self.beam_data.items():
            fx = self.rx_data[i].fx_count
            if fx:
                for beam in beamset:
                    if beam.meter_set:
                        mus.append(beam.meter_set * fx)
        return sum(mus)

    @property
    def heterogeneity_correction(self):
        if hasattr(self.rt_data['dose'], 'TissueHeterogeneityCorrection'):
            if isinstance(self.rt_data['dose'].TissueHeterogeneityCorrection, str):
                heterogeneity_correction = self.rt_data['dose'].TissueHeterogeneityCorrection
            else:
                heterogeneity_correction = ','.join(self.rt_data['dose'].TissueHeterogeneityCorrection)
        else:
            heterogeneity_correction = 'IMAGE'

        return heterogeneity_correction

    @property
    def patient_sex(self):
        return self.get_attribute('plan', 'PatientSex')

    @property
    def sim_study_date(self):
        return self.get_date('plan', 'StudyDate')

    @property
    def birth_date(self):
        return self.get_date('plan', 'PatientBirthDate')

    @property
    def age(self):
        if self.sim_study_date and self.birth_date:
            age = relativedelta(self.sim_study_date, self.birth_date).years
            if age <= 0:
                return None
            return age

    @property
    def physician(self):
        return self.get_attribute('plan', ['PhysiciansOfRecord', 'ReferringPhysicianName'])

    @property
    def fxs(self):
        try:
            fx_grp_seq = self.rt_data['plan'].FractionGroupSequence
            return [int(float(fx_grp.NumberOfFractionsPlanned)) for fx_grp in fx_grp_seq]
        except ValueError:
            return None

    @property
    def fxs_total(self):
        fxs = self.fxs
        if fxs:
            return sum(fxs)
        return None

    @property
    def fx_grp_count(self):
        return len(self.rt_data['plan'].FractionGroupSequence)

    @property
    def patient_orientation(self):
        return ','.join(self.get_attribute('plan', 'PatientSetupSequence'))

    @property
    def plan_time_stamp(self):
        return self.get_time_stamp('plan', 'RTPlanDate', 'RTPlanTime')

    @property
    def struct_time_stamp(self):
        return self.get_time_stamp('structure', 'StructureSetDate', 'StructureSetTime')

    @property
    def dose_time_stamp(self):
        return self.get_time_stamp('dose', 'InstanceCreationDate', 'InstanceCreationTime', round_seconds=True)

    @property
    def tps_manufacturer(self):
        return self.get_attribute('plan', 'Manufacturer')

    @property
    def tps_software_name(self):
        return self.get_attribute('plan', 'ManufacturerModelName')

    @property
    def tps_software_version(self):
        return ','.join(self.get_attribute('plan', 'SoftwareVersions'))

    @property
    def tx_site(self):
        return self.get_attribute('plan', 'RTPlanLabel')

    @property
    def brachy(self):
        return hasattr(self.rt_data['plan'], 'BrachyTreatmentType')

    @property
    def brachy_type(self):
        return self.get_attribute('plan', 'BrachyTreatmentType')

    @property
    def proton(self):
        return hasattr(self.rt_data['plan'], 'IonBeamSequence')

    @property
    def beam_sequence(self):
        if hasattr(self.rt_data['plan'], 'BeamSequence'):
            return self.rt_data['plan'].BeamSequence
        elif hasattr(self.rt_data['plan'], 'IonBeamSequence'):
            return self.rt_data['plan'].IonBeamSequence
        return None

    @property
    def photon(self):
        return self.is_photon_or_electron('photon')

    @property
    def electron(self):
        return self.is_photon_or_electron('electron')

    @property
    def radiation_type(self):
        rad_types = {'PHOTONS': self.photon,
                     'ELECTRONS': self.electron,
                     'PROTONS': self.proton,
                     'BRACHY': self.brachy_type}
        types = [rad_type for rad_type, rad_value in rad_types.items() if rad_value]
        return ','.join(types)

    @property
    def tx_time(self):
        if hasattr(self.rt_data['plan'], 'BrachyTreatmentType') and \
                hasattr(self.rt_data['plan'], 'ApplicationSetupSequence'):
            seconds = 0
            for app_seq in self.rt_data['plan'].ApplicationSetupSequence:
                for chan_seq in app_seq.ChannelSequence:
                    seconds += chan_seq.ChannelTotalTime
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            return "%02d:%02d:%02d" % (h, m, s)
        return '00:00:00'

    @property
    def dose_grid_res(self):
        try:
            dose_grid_resolution = [str(round(float(self.rt_data['dose'].PixelSpacing[0]), 1)),
                                    str(round(float(self.rt_data['dose'].PixelSpacing[1]), 1))]
            if hasattr(self.rt_data['dose'], 'SliceThickness') and self.rt_data['dose'].SliceThickness:
                dose_grid_resolution.append(str(round(float(self.rt_data['dose'].SliceThickness), 1)))
            return ', '.join(dose_grid_resolution)
        except:
            return None

    # ------------------------------------------------------------------------------
    # DVH table data
    # ------------------------------------------------------------------------------
    def get_dvh(self, key):
        dvhcalc.get_dvh(self.rt_data['structure'], self.rt_data['dose'], key)

    def get_roi_type(self, key):
        # ITV is not currently in any TPS as an ROI type.  If the ROI begins with ITV, DVH assumes
        # a ROI type of ITV
        if self.dicompyler_rt_structures[key]['name'].lower()[0:3] == 'itv':
            return 'ITV'
        else:
            return self.dicompyler_rt_structures[key]['type'].upper()

    def get_roi_name(self, key):
        return clean_name(self.dicompyler_rt_structures[key]['name'])

    def get_physician_roi(self, key):
        roi_name = self.get_roi_name(key)
        if self.database_rois.is_roi(roi_name):
            if self.database_rois.is_physician(self.physician):
                return self.database_rois.get_physician_roi(self.physician, roi_name)
        return 'uncategorized'

    def get_institutional_roi(self, key):
        roi_name = self.get_roi_name(key)
        if self.database_rois.is_roi(roi_name):
            if self.database_rois.is_physician(self.physician):
                return self.database_rois.get_institutional_roi(self.physician, self.get_physician_roi(key))
            if roi_name in self.database_rois.institutional_rois:
                return roi_name
        return 'uncategorized'

    def get_surface_area(self, key):
        coord = self.dicompyler_data['structure'].GetStructureCoordinates(key)
        try:
            return roi_calc.surface_area(coord)
        except:
            print("Surface area calculation failed for key, name: %s, %s" % (key, self.get_roi_name(key)))
            return None

    def get_dvh_geometries(self, key):
        structure_coord = self.dicompyler_data['structure'].GetStructureCoordinates(key)
        roi_coord_str = dicompyler_roi_coord_to_db_string(structure_coord)
        planes = get_planes_from_string(roi_coord_str)
        coord = self.dicompyler_data['structure'].GetStructureCoordinates(key)

        try:
            surface_area = roi_calc.surface_area(coord)
        except:
            print("Surface area calculation failed for key, name: %s, %s" % (key, self.get_roi_name(key)))
            surface_area = None

        centroid = roi_calc.centroid(planes)
        spread = roi_calc.spread(planes)
        cross_sections = roi_calc.cross_section(planes)

        return {'roi_coord_str': roi_coord_str,
                'surface_area': surface_area,
                'centroid': centroid,
                'spread': spread,
                'cross_sections': cross_sections}

    # ------------------------------------------------------------------------------
    # Generic tools
    # ------------------------------------------------------------------------------
    def get_attribute(self, rt_type, pydicom_attribute):
        """
        :param rt_type: plan. dose, or structure
        :type rt_type: str
        :param pydicom_attribute: attribute as specified in pydicom
        :type pydicom_attribute: str or list of str
        :return: pydicom value or None
        """
        if isinstance(pydicom_attribute, str):
            pydicom_attribute = [pydicom_attribute]

        for attribute in pydicom_attribute:
            if hasattr(self.rt_data[rt_type], attribute):
                return getattr(self.rt_data[rt_type], attribute)
        return None

    def get_date(self, rt_type, pydicom_attribute, include_time=False):
        """
        :param rt_type: plan. dose, or structure
        :type rt_type: str
        :param pydicom_attribute: attribute as specified in pydicom
        :type pydicom_attribute: str
        :param include_time: if true, include timestamp, otherwise year, month, date
        :type include_time: bool
        :return: datetime object of pydicom string
        :rtype: datetime
        """
        ans = self.get_attribute(rt_type, pydicom_attribute)
        if ans:
            try:
                if include_time:
                    return datetime_str_to_obj(ans)
                return date_str_to_obj(ans)
            except ValueError:
                print('ValueError: Could not parse %s to datetime' % ans)
            finally:
                print('Could not parse %s to datetime' % ans)
        return None

    def get_time_stamp(self, rt_type, date_attribute, time_attribute, round_seconds=False):
        date = self.get_attribute(rt_type, date_attribute)
        time = self.get_attribute(rt_type, time_attribute)
        try:
            if round_seconds:
                date = date.split('.')[0]
            return datetime_str_to_obj(date + time)
        except ValueError:
            return date_str_to_obj(date)
        finally:
            return None

    def is_photon_or_electron(self, rad_type):
        if hasattr(self.rt_data['plan'], 'BeamSequence'):
            for beam in self.rt_data['plan'].BeamSequence:
                if rad_type in beam.RadiationType:
                    return True
        return False


class BeamParser:
    def __init__(self, rt_plan, fx_grp_index, beam_index):
        self.rt_plan = rt_plan
        self.fx_grp_index = fx_grp_index
        self.fx_grp_data = rt_plan.FractionGroupSequence[fx_grp_index]
        self.beam_index = beam_index
        self.ref_beam_index = self.get_ref_beam_index()

        self.cp_seq = None
        if hasattr(rt_plan, 'BeamSequence'):
            self.beam_data = rt_plan.BeamSequence[beam_index]  # Photons and electrons
            if hasattr(self.beam_data, 'ControlPointSequence'):
                self.cp_seq = self.beam_data.ControlPointSequence
        elif hasattr(rt_plan, 'IonBeamSequence'):
            self.beam_data = rt_plan.IonBeamSequence[beam_index]  # Protons
            if hasattr(self.beam_data, 'IonControlPointSequence'):
                self.cp_seq = self.beam_data.IonControlPointSequence
        else:
            print('ERROR: BeamSequence nor IonBeamSequence found in fx_grp_number %s, beam_index %s' %
                  (fx_grp_index, beam_index))
            self.beam_data = None

        self.ref_beam_data = self.fx_grp_data.ReferencedBeamSequence[self.ref_beam_index]

    @property
    def beam_number(self):
        return self.beam_data.BeamNumber

    @property
    def beam_name(self):
        return self.beam_data.BeamDescription

    def get_ref_beam_index(self):
        ref_beam_seq = self.rt_plan.FractionGroupSequence[self.fx_grp_index].ReferencedBeamSequence
        for i, ref_beam in enumerate(ref_beam_seq):
            if ref_beam.ReferencedBeamNumber == self.beam_number:
                return i
        print('ERROR: Failed to find a matching reference beam in '
              'ReferencedBeamSequence for beam number %s' % self.beam_number)
        print('WARNING: Assuming reference beam index is equal to beam number may lead to incorrect'
              ' MUs and beam doses reported in SQL database.  Please verify')
        return self.beam_number

    @property
    def treatment_machine(self):
        return self.get_data_attribute(self.beam_data, 'TreatmentMachineName')

    @property
    def beam_dose(self):
        return self.get_data_attribute(self.ref_beam_data, 'BeamDose', default=0., data_type='float')

    @property
    def beam_mu(self):
        return self.get_data_attribute(self.ref_beam_data, 'BeamMeterset', default=0., data_type='float')

    @property
    def beam_dose_pt(self):
        return self.get_point_attribute(self.ref_beam_data, 'BeamDoseSpecificationPoint')

    @property
    def isocenter(self):
        return self.get_point_attribute(self.cp_seq[0], 'IsocenterPosition')

    @property
    def beam_type(self):
        return self.get_data_attribute(self.beam_data, 'BeamType')

    @property
    def radiation_type(self):
        return self.get_data_attribute(self.beam_data, 'RadiationType')

    @property
    def scan_mode(self):
        return self.get_data_attribute(self.beam_data, 'ScanMode')

    @property
    def scan_spot_count(self):
        if hasattr(self.cp_seq[0], 'NumberOfScanSpotPositions'):
            return sum([int(cp.NumberOfScanSpotPositions) for cp in self.cp_seq]) / 2
        return None

    @property
    def energies(self):
        return self.get_cp_attributes('NominalBeamEnergy')

    @property
    def energy_min(self):
        return round(min(self.energies), 2)

    @property
    def energy_max(self):
        return round(max(self.energies), 2)

    @property
    def gantry_angles(self):
        return self.get_cp_attributes('GantryAngle')

    @property
    def collimator_angles(self):
        return self.get_cp_attributes('BeamLimitingDeviceAngle')

    @property
    def couch_angles(self):
        return self.get_cp_attributes('PatientSupportAngle')

    @property
    def gantry_rot_dirs(self):
        return self.get_cp_attributes('GantryRotationDirection')

    @property
    def collimator_rot_dirs(self):
        return self.get_cp_attributes('BeamLimitingDeviceRotationDirection')

    @property
    def couch_rot_dirs(self):
        return self.get_cp_attributes('PatientSupportRotationDirection')

    @staticmethod
    def get_rotation_direction(rotation_list):
        if len(set(rotation_list)) == 1:  # Only one direction found
            return rotation_list[0]
        return ['CC/CW', 'CW/CC'][rotation_list[0] == 'CW']

    @property
    def gantry_values(self):
        return self.get_angle_values('gantry')

    @property
    def collimator_values(self):
        return self.get_angle_values('collimator')

    @property
    def couch_values(self):
        return self.get_angle_values('couch')

    def get_angle_values(self, angle_type):
        angles = getattr(self, '%s_angle' % angle_type)
        return {'start': angles[0],
                'end': angles[-1],
                'rot_dir': self.get_rotation_direction(getattr(self, '%s_rot_dirs' % angle_type)),
                'range': round(float(np.sum(np.abs(np.diff(angles)))), 1),
                'min': min(angles),
                'max': max(angles)}

    @property
    def is_arc(self):
        return bool(len(set(self.gantry_angles)))  # if multiple gantry angles, beam is an arc

    @property
    def tx_modality(self):
        rad_type = str(self.radiation_type)
        if not rad_type:
            return None
        if 'brachy' in rad_type.lower():
            return rad_type
        return "%s %s" % (self.radiation_type.title(), ['3D', 'Arc'][self.is_arc])

    @property
    def control_point_count(self):
        return self.get_data_attribute(self.beam_data, 'NumberOfControlPoints')

    @property
    def ssd(self):
        ssds = self.get_cp_attributes('SourceToSurfaceDistance')
        if ssds:
            return round(float(np.average(ssds))/10., 2)
        return None

    @property
    def beam_mu_per_deg(self):
        try:
            return round(self.beam_mu / self.gantry_values['range'], 2)
        except:
            return None

    @property
    def beam_mu_per_cp(self):
        try:
            return round(self.beam_mu / self.control_point_count, 2)
        except:
            return None

    @property
    def mlc_stat_data(self):
        mlc_keys = ['area', 'x_perim', 'y_perim', 'cmp_score', 'cp_mu']
        try:
            mlc_summary_data = mlca(self.beam_data, self.beam_mu, ignore_zero_mu_cp=True).summary
            mlca_stat_data = {key: calc_stats(mlc_summary_data[key]) for key in mlc_keys}
            mlca_stat_data['complexity'] = np.sum(mlc_summary_data['cmp_score'])
        except:
            mlca_stat_data = {key: ['NULL'] * 6 for key in mlc_keys}
            mlca_stat_data['complexity'] = None
        return mlca_stat_data

    @staticmethod
    def get_data_attribute(data_obj, pydicom_attr, default=None, data_type=None):
        if hasattr(data_obj, pydicom_attr):
            value = getattr(data_obj, pydicom_attr)
            if data_type == 'float':
                return float(value)
            elif data_type == 'int':
                return int(float(value))
            return value
        return default

    def get_point_attribute(self, data_obj, pydicom_attr):
        point = self.get_data_attribute(data_obj, pydicom_attr)
        if point:
            return ','.join([str(round(dim_value, 2)) for dim_value in point])
        return None

    def get_cp_attributes(self, pydicom_attr):
        values = []
        for cp in self.cp_seq:
            if hasattr(cp, pydicom_attr):
                if 'Rotation' in pydicom_attr:
                    if getattr(cp, pydicom_attr).upper() in {'CC', 'CW'}:
                        values.append(getattr(cp, pydicom_attr).upper())
                else:
                    values.append(getattr(cp, pydicom_attr))
        if pydicom_attr[-5:] == 'Angle':
            values = change_angle_origin(values, 180)
        return values


class RxParser:
    def __init__(self, rt_plan, dicompyler_plan, rt_structure, fx_grp_index):
        self.rt_plan = rt_plan
        self.dicompyler_plan = dicompyler_plan
        self.rt_structure = rt_structure
        self.fx_grp_data = rt_plan.FractionGroupSequence[fx_grp_index]
        self.dose_ref_index = self.get_dose_ref_seq_index()

    @property
    def plan_name(self):
        if hasattr(self.rt_plan, 'RTPlanLabel'):
            return self.rt_plan.RTPlanLabel
        return None

    @property
    def fx_grp_number(self):
        return self.fx_grp_data.FractionGroupNumber

    @property
    def fx_grp_name(self):
        return "FxGrp %s" % self.fx_grp_number

    @property
    def has_dose_ref(self):
        return hasattr(self.rt_plan, 'DoseReferenceSequence')

    def get_dose_ref_seq_index(self):
        for i, dose_ref in enumerate(self.rt_plan.DoseReferenceSequence):
            if dose_ref.DoseReferenceNumber == self.fx_grp_number:
                return i
        print('WARNING: DoseReference not found, verification of rx dose attributes recommended')
        return None

    @property
    def rx_dose(self):
        ans = self.get_dose_ref_attr('TargetPrescriptionDose')
        if ans is None:
            ans = float(self.dicompyler_plan['rxdose']) / 100.
        return ans

    @property
    def fx_count(self):
        return self.fx_grp_data.NumberOfFractionsPlanned

    @property
    def fx_dose(self):
        try:
            return round(self.rx_dose / float(self.fx_count), 2)
        except:
            print('WARNING: Unable to calculate fx_dose')
            return None

    @property
    def normalization_method(self):
        return self.get_dose_ref_attr('DoseReferenceStructureType')

    def get_dose_ref_attr(self, pydicom_attr):
        if self.has_dose_ref and self.dose_ref_index is not None:
            dose_ref_data = self.rt_plan.DoseReferenceSequence[self.dose_ref_index]
            if hasattr(dose_ref_data, pydicom_attr):
                return getattr(dose_ref_data, pydicom_attr)
        return None

    @property
    def normalization_object(self):
        if self.normalization_method:
            if self.normalization_method.lower() == 'coordinates':
                return 'COORDINATE'
            elif self.normalization_method.lower() == 'site':
                if hasattr(self.rt_plan, 'ManufacturerModelName'):
                    return self.rt_plan.ManufacturerModelName
        return None

    @property
    def beam_count(self):
        if hasattr(self.fx_grp_data, 'NumberOfBeams'):
            return self.fx_grp_data.NumberOfBeams
        return None
