import wx
import wx.adv
from dateutil.parser import parse as parse_date
from tools.utilities import get_selected_listctrl_items, MessageDialog
from db import sql_columns
from db.sql_connector import DVH_SQL
import matplotlib.colors as plot_colors
from os.path import isdir
from paths import IMPORT_SETTINGS_PATH, parse_settings_file


class DatePicker(wx.Dialog):
    def __init__(self, title='', initial_date=None):
        wx.Dialog.__init__(self, None, title=title)

        self.calendar_ctrl = wx.adv.CalendarCtrl(self, wx.ID_ANY,
                                                 style=wx.adv.CAL_SHOW_HOLIDAYS | wx.adv.CAL_SHOW_SURROUNDING_WEEKS)
        if initial_date:
            self.calendar_ctrl.SetDate(parse_date(initial_date))

        self.button = {'apply': wx.Button(self, wx.ID_OK, "Apply"),
                       'delete': wx.Button(self, wx.ID_ANY, "Delete"),
                       'cancel': wx.Button(self, wx.ID_CANCEL, "Cancel")}

        self.none = False

        self.__do_layout()
        self.__do_bind()

    def __do_layout(self):
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_main = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main.Add(self.calendar_ctrl, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        for button in self.button.values():
            sizer_buttons.Add(button, 0, wx.ALL, 5)
        sizer_main.Add(sizer_buttons, 1, wx.ALIGN_CENTER | wx.BOTTOM | wx.TOP, 10)
        sizer_wrapper.Add(sizer_main, 1, wx.ALL | wx.EXPAND, 10)
        self.SetSizer(sizer_wrapper)
        sizer_wrapper.Fit(self)
        self.Layout()
        self.Center()

    def __do_bind(self):
        self.Bind(wx.EVT_BUTTON, self.on_delete, id=self.button['delete'].GetId())

    @property
    def date(self):
        if self.none:
            return ''
        date = self.calendar_ctrl.GetDate()
        return "%s/%s/%s" % (date.month+1, date.day, date.year)

    def on_delete(self, evt):
        self.none = True
        self.Close()


class AddEndpointDialog(wx.Dialog):
    def __init__(self, *args, **kwds):
        wx.Dialog.__init__(self, None, title=kwds['title'])

        self.combo_box_output = wx.ComboBox(self, wx.ID_ANY,
                                            choices=["Dose (Gy)", "Dose(%)", "Volume (cc)", "Volume (%)"],
                                            style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.text_input = wx.TextCtrl(self, wx.ID_ANY, "")
        self.radio_box_units = wx.RadioBox(self, wx.ID_ANY, "", choices=["cc ", "% "], majorDimension=1,
                                           style=wx.RA_SPECIFY_ROWS)
        self.button_ok = wx.Button(self, wx.ID_OK, "OK")
        self.button_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")

        self.Bind(wx.EVT_COMBOBOX, self.combo_box_ticker, id=self.combo_box_output.GetId())
        self.Bind(wx.EVT_TEXT, self.text_input_ticker, id=self.text_input.GetId())
        self.Bind(wx.EVT_RADIOBOX, self.radio_box_ticker, id=self.radio_box_units.GetId())

        self.__set_properties()
        self.__do_layout()

    def __set_properties(self):
        self.radio_box_units.SetSelection(0)
        self.combo_box_output.SetValue('Dose (Gy)')

    def __do_layout(self):
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons_wrapper = wx.BoxSizer(wx.HORIZONTAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_input = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.HORIZONTAL)
        sizer_input_units = wx.BoxSizer(wx.VERTICAL)
        sizer_input_value = wx.BoxSizer(wx.VERTICAL)
        sizer_output = wx.BoxSizer(wx.VERTICAL)
        label_ouput = wx.StaticText(self, wx.ID_ANY, "Output:")
        sizer_output.Add(label_ouput, 0, wx.BOTTOM | wx.EXPAND, 8)
        sizer_output.Add(self.combo_box_output, 0, wx.EXPAND, 0)
        sizer_input.Add(sizer_output, 1, wx.ALL | wx.EXPAND, 5)
        self.label_input_value = wx.StaticText(self, wx.ID_ANY, "Input Volume (cc):")
        sizer_input_value.Add(self.label_input_value, 0, wx.BOTTOM | wx.EXPAND, 8)
        sizer_input_value.Add(self.text_input, 0, wx.EXPAND | wx.LEFT, 5)
        sizer_input.Add(sizer_input_value, 1, wx.ALL | wx.EXPAND, 5)
        label_input_units = wx.StaticText(self, wx.ID_ANY, "Input Units:")
        sizer_input_units.Add(label_input_units, 0, wx.BOTTOM | wx.EXPAND, 3)
        sizer_input_units.Add(self.radio_box_units, 0, wx.EXPAND, 0)
        sizer_input.Add(sizer_input_units, 1, wx.ALL | wx.EXPAND, 5)
        sizer_wrapper.Add(sizer_input, 0, wx.ALL | wx.EXPAND, 10)
        self.text_short_hand = wx.StaticText(self, wx.ID_ANY, "\tShort-hand: ")
        sizer_wrapper.Add(self.text_short_hand, 0, wx.ALL, 5)
        sizer_buttons.Add(self.button_ok, 0, wx.ALL, 5)
        sizer_buttons.Add(self.button_cancel, 0, wx.ALL | wx.EXPAND, 5)
        sizer_buttons_wrapper.Add(sizer_buttons, 0, wx.ALL | wx.EXPAND, 5)
        sizer_wrapper.Add(sizer_buttons_wrapper, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.SetSizer(sizer_wrapper)
        sizer_wrapper.Fit(self)
        self.Layout()
        self.Center()

    def combo_box_ticker(self, evt):
        self.update_radio_box_choices()
        self.update_label_input()
        self.update_short_hand()

    def text_input_ticker(self, evt):
        self.update_short_hand()

    def radio_box_ticker(self, evt):
        self.update_label_input()
        self.update_short_hand()

    def update_label_input(self):
        new_label = "%s (%s):" % (['Input Dose', 'Input Volume']['Dose' in self.combo_box_output.GetValue()],
                                  self.radio_box_units.GetItemLabel(self.radio_box_units.GetSelection()))
        self.label_input_value.SetLabelText(new_label)

    def update_radio_box_choices(self):
        choice_1 = ['Gy', 'cc']['Dose' in self.combo_box_output.GetValue()]
        self.radio_box_units.SetItemLabel(0, choice_1)

    def update_short_hand(self):
        short_hand = ['\tShort-hand: ']
        if self.text_input.GetValue():
            try:
                str(float(self.text_input.GetValue()))
                short_hand.extend([['V_', 'D_']['Dose' in self.combo_box_output.GetValue()],
                                   self.text_input.GetValue(),
                                   self.radio_box_units.GetItemLabel(self.radio_box_units.GetSelection()).strip()])
            except ValueError:
                pass
        self.text_short_hand.SetLabelText(''.join(short_hand))

    @property
    def is_endpoint_valid(self):
        return bool(len(self.short_hand_label))

    @property
    def short_hand_label(self):
        return self.text_short_hand.GetLabel().replace('\tShort-hand: ', '').strip()

    @property
    def output_type(self):
        return ['absolute', 'relative']['%' in self.combo_box_output.GetValue()]

    @property
    def input_type(self):
        return ['absolute', 'relative'][self.radio_box_units.GetSelection()]

    @property
    def units_in(self):
        return self.radio_box_units.GetItemLabel(self.radio_box_units.GetSelection()).replace('%', '').strip()

    @property
    def units_out(self):
        return self.combo_box_output.GetValue().split('(')[1][:-1].replace('%', '').strip()

    @property
    def input_value(self):
        try:
            return float(self.text_input.GetValue())
        except ValueError:
            return 0.

    @property
    def endpoint_row(self):
        return [self.short_hand_label,
                self.output_type,
                self.input_type,
                self.input_value,
                self.units_in,
                self.units_out]


class DelEndpointDialog(wx.Dialog):
    def __init__(self, endpoints, *args, **kwds):
        wx.Dialog.__init__(self, None, title='Delete Endpoint')

        self.endpoints = endpoints

        self.list_ctrl_endpoints = wx.ListCtrl(self, wx.ID_ANY, style=wx.LC_REPORT)
        self.button_select_all = wx.Button(self, wx.ID_ANY, "Select All")
        self.button_deselect_all = wx.Button(self, wx.ID_ANY, "Deselect All")
        self.button_ok = wx.Button(self, wx.ID_OK, "OK")
        self.button_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")

        self.Bind(wx.EVT_BUTTON, self.select_all, id=self.button_select_all.GetId())
        self.Bind(wx.EVT_BUTTON, self.deselect_all, id=self.button_deselect_all.GetId())

        self.__set_properties()
        self.__do_layout()

    def __set_properties(self):
        self.list_ctrl_endpoints.AppendColumn("Endpoint", format=wx.LIST_FORMAT_LEFT, width=200)

        for ep in self.endpoints:
            if ep not in {'MRN', 'Tx Site', 'ROI Name'}:
                self.list_ctrl_endpoints.InsertItem(50000, ep)

    def __do_layout(self):
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_ok_cancel = wx.BoxSizer(wx.HORIZONTAL)
        sizer_select = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_select_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_select.Add(self.list_ctrl_endpoints, 0, wx.ALL | wx.EXPAND, 5)
        sizer_select_buttons.Add(self.button_select_all, 0, wx.ALL, 5)
        sizer_select_buttons.Add(self.button_deselect_all, 0, wx.ALL, 5)
        sizer_select.Add(sizer_select_buttons, 0, wx.ALIGN_CENTER | wx.ALL, 0)
        sizer_wrapper.Add(sizer_select, 0, wx.ALL | wx.EXPAND, 5)
        sizer_ok_cancel.Add(self.button_ok, 0, wx.ALL, 5)
        sizer_ok_cancel.Add(self.button_cancel, 0, wx.ALL, 5)
        sizer_wrapper.Add(sizer_ok_cancel, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        self.SetSizer(sizer_wrapper)
        sizer_wrapper.Fit(self)
        self.Layout()

    @property
    def selected_indices(self):
        return get_selected_listctrl_items(self.list_ctrl_endpoints)

    @property
    def selected_values(self):
        return [self.list_ctrl_endpoints.GetItem(i, 0).GetText() for i in self.selected_indices]

    @property
    def endpoint_count(self):
        return len(self.endpoints)-2

    def select_all(self, evt):
        self.apply_global_selection()

    def deselect_all(self, evt):
        self.apply_global_selection(on=0)

    def apply_global_selection(self, on=1):
        for i in range(self.endpoint_count):
            self.list_ctrl_endpoints.Select(i, on=on)


def query_dlg(parent, query_type, title=None, set_values=False):
    dlg = {'categorical': QueryCategoryDialog,
           'numerical': QueryNumericalDialog}[query_type](title=title)
    data_table = {'categorical': parent.data_table_categorical,
                  'numerical': parent.data_table_numerical}[query_type]
    selected_index = {'categorical': parent.selected_index_categorical,
                      'numerical': parent.selected_index_numerical}[query_type]
    if set_values:
        dlg.set_values(data_table.get_row(selected_index))

    res = dlg.ShowModal()
    if res == wx.ID_OK:
        row = dlg.get_values()
        if set_values:
            data_table.edit_row(row, selected_index)
        else:
            data_table.append_row(row)
        parent.update_all_query_buttons()
    dlg.Destroy()


class QueryCategoryDialog(wx.Dialog):

    def __init__(self, *args, **kw):
        wx.Dialog.__init__(self, None)

        if 'title' in kw and kw['title']:
            self.SetTitle(kw['title'])
        else:
            self.SetTitle('Query by Categorical Data')

        self.selector_categories = sql_columns.categorical

        selector_options = list(self.selector_categories)
        selector_options.sort()

        self.combo_box_1 = wx.ComboBox(self, wx.ID_ANY, choices=selector_options, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.combo_box_2 = wx.ComboBox(self, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.checkbox_1 = wx.CheckBox(self, wx.ID_ANY, "Exclude")
        self.button_OK = wx.Button(self, wx.ID_OK, "OK")
        self.button_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")

        self.__do_layout()

        self.combo_box_1.SetValue('ROI Institutional Category')
        self.update_category_2(None)
        self.Bind(wx.EVT_COMBOBOX, self.update_category_2, id=self.combo_box_1.GetId())

        self.Fit()
        self.Center()

    def __do_layout(self):
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_vbox = wx.BoxSizer(wx.VERTICAL)
        sizer_ok_cancel = wx.BoxSizer(wx.HORIZONTAL)
        sizer_widgets = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.HORIZONTAL)
        sizer_category_2 = wx.BoxSizer(wx.VERTICAL)
        sizer_category_1 = wx.BoxSizer(wx.VERTICAL)
        label_category_1 = wx.StaticText(self, wx.ID_ANY, "Category 1:")
        sizer_category_1.Add(label_category_1, 0, wx.ALL | wx.EXPAND, 5)
        sizer_category_1.Add(self.combo_box_1, 0, wx.ALL, 5)
        sizer_widgets.Add(sizer_category_1, 1, wx.EXPAND, 0)
        label_category_2 = wx.StaticText(self, wx.ID_ANY, "Category 2:")
        sizer_category_2.Add(label_category_2, 0, wx.ALL | wx.EXPAND, 5)
        sizer_category_2.Add(self.combo_box_2, 0, wx.EXPAND | wx.ALL, 5)
        sizer_widgets.Add(sizer_category_2, 1, wx.EXPAND, 0)
        sizer_widgets.Add(self.checkbox_1, 0, wx.ALL | wx.EXPAND, 5)
        sizer_vbox.Add(sizer_widgets, 0, wx.ALL | wx.EXPAND, 5)
        sizer_ok_cancel.Add(self.button_OK, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer_ok_cancel.Add(self.button_cancel, 0, wx.LEFT | wx.RIGHT, 5)
        sizer_vbox.Add(sizer_ok_cancel, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_wrapper.Add(sizer_vbox, 0, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(sizer_wrapper)

    def update_category_2(self, evt):
        key = self.combo_box_1.GetValue()
        table = self.selector_categories[key]['table']
        col = self.selector_categories[key]['var_name']
        with DVH_SQL() as cnx:
            options = cnx.get_unique_values(table, col)
        self.combo_box_2.Clear()
        self.combo_box_2.Append(options)
        if options:
            self.combo_box_2.SetValue(options[0])

    def set_category_1(self, value):
        self.combo_box_1.SetValue(value)
        self.update_category_2(None)

    def set_category_2(self, value):
        self.combo_box_2.SetValue(value)

    def set_check_box_not(self, value):
        self.checkbox_1.SetValue(value)

    def set_values(self, values):
        self.set_category_1(values[0])
        self.set_category_2(values[1])
        self.set_check_box_not({'Include': False, 'Exclude': True}[values[2]])

    def get_values(self):
        return [self.combo_box_1.GetValue(),
                self.combo_box_2.GetValue(),
                ['Include', 'Exclude'][self.checkbox_1.GetValue()]]


class QueryNumericalDialog(wx.Dialog):

    def __init__(self, *args, **kw):
        wx.Dialog.__init__(self, None)

        if 'title' in kw and kw['title']:
            self.SetTitle(kw['title'])
        else:
            self.SetTitle('Query by Numerical Data')

        self.numerical_categories = sql_columns.numerical

        numerical_options = list(self.numerical_categories)
        numerical_options.sort()

        self.combo_box_1 = wx.ComboBox(self, wx.ID_ANY, choices=numerical_options, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.text_ctrl_min = wx.TextCtrl(self, wx.ID_ANY, "")
        self.text_ctrl_max = wx.TextCtrl(self, wx.ID_ANY, "")
        self.checkbox_1 = wx.CheckBox(self, wx.ID_ANY, "Exclude")
        self.button_OK = wx.Button(self, wx.ID_OK, "OK")
        self.button_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")

        self.combo_box_1.SetValue("ROI Max Dose")
        self.update_range(None)

        self.Bind(wx.EVT_COMBOBOX, self.update_range, id=self.combo_box_1.GetId())

        self.__do_layout()

    def __do_layout(self):
        # begin wxGlade: MyFrame.__do_layout
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_vbox = wx.BoxSizer(wx.VERTICAL)
        sizer_ok_cancel = wx.BoxSizer(wx.HORIZONTAL)
        sizer_widgets = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.HORIZONTAL)
        sizer_max = wx.BoxSizer(wx.VERTICAL)
        sizer_min = wx.BoxSizer(wx.VERTICAL)
        sizer_category_1 = wx.BoxSizer(wx.VERTICAL)
        label_category = wx.StaticText(self, wx.ID_ANY, "Category:")
        sizer_category_1.Add(label_category, 0, wx.ALL | wx.EXPAND, 5)
        sizer_category_1.Add(self.combo_box_1, 0, wx.ALL, 5)
        sizer_widgets.Add(sizer_category_1, 1, wx.EXPAND, 0)
        label_min = wx.StaticText(self, wx.ID_ANY, "Min:")
        sizer_min.Add(label_min, 0, wx.ALL | wx.EXPAND, 5)
        sizer_min.Add(self.text_ctrl_min, 0, wx.ALL, 5)
        sizer_widgets.Add(sizer_min, 0, wx.EXPAND, 0)
        label_max = wx.StaticText(self, wx.ID_ANY, "Max:")
        sizer_max.Add(label_max, 0, wx.ALL | wx.EXPAND, 5)
        sizer_max.Add(self.text_ctrl_max, 0, wx.ALL, 5)
        sizer_widgets.Add(sizer_max, 0, wx.EXPAND, 0)
        sizer_widgets.Add(self.checkbox_1, 0, wx.ALL | wx.EXPAND, 5)
        sizer_vbox.Add(sizer_widgets, 0, wx.ALL | wx.EXPAND, 5)
        sizer_ok_cancel.Add(self.button_OK, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer_ok_cancel.Add(self.button_cancel, 0, wx.LEFT | wx.RIGHT, 5)
        sizer_vbox.Add(sizer_ok_cancel, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        sizer_wrapper.Add(sizer_vbox, 0, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(sizer_wrapper)

        self.Fit()
        self.Center()

    def update_range(self, evt):
        key = self.combo_box_1.GetValue()
        table = self.numerical_categories[key]['table']
        col = self.numerical_categories[key]['var_name']
        units = self.numerical_categories[key]['units']
        with DVH_SQL() as cnx:
            min_value = cnx.get_min_value(table, col)
            max_value = cnx.get_max_value(table, col)

        if units:
            self.text_ctrl_min.SetLabelText('Min (%s):' % units)
            self.text_ctrl_max.SetLabelText('Max (%s):' % units)
        else:
            self.text_ctrl_min.SetLabelText('Min:')
            self.text_ctrl_max.SetLabelText('Max:')
        self.set_min_value(min_value)
        self.set_max_value(max_value)

    def set_category(self, value):
        self.combo_box_1.SetValue(value)
        self.update_range(None)

    def set_min_value(self, value):
        self.text_ctrl_min.SetValue(str(value))

    def set_max_value(self, value):
        self.text_ctrl_max.SetValue(str(value))

    def set_check_box_not(self, value):
        self.checkbox_1.SetValue(value)

    def set_values(self, values):
        self.set_category(values[0])
        self.set_min_value(str(values[1]))
        self.set_max_value(str(values[2]))
        self.set_check_box_not({'Include': False, 'Exclude': True}[values[3]])

    def get_values(self):
        return [self.combo_box_1.GetValue(),
                self.text_ctrl_min.GetValue(),
                self.text_ctrl_max.GetValue(),
                ['Include', 'Exclude'][self.checkbox_1.GetValue()]]

    def validated_text(self, input_type):
        old_value = {'min': self.text_ctrl_min.GetValue(), 'max': self.text_ctrl_max.GetValue()}[input_type]

        try:
            new_value = float(old_value)
        except ValueError:
            key = self.combo_box_1.GetValue()
            table = self.numerical_categories[key]['table']
            col = self.numerical_categories[key]['var_name']
            with DVH_SQL() as cnx:
                if input_type == 'min':
                    new_value = cnx.get_min_value(table, col)
                else:
                    new_value = cnx.get_max_value(table, col)
        return new_value


class UserSettings(wx.Dialog):
    def __init__(self, options):
        wx.Dialog.__init__(self, None, title="User Settings")

        self.options = options

        colors = list(plot_colors.cnames)
        colors.sort()

        color_variables = self.get_option_choices('COLOR')
        size_variables = self.get_option_choices('SIZE')
        width_variables = self.get_option_choices('LINE_WIDTH')
        line_dash_variables = self.get_option_choices('LINE_DASH')
        alpha_variables = self.get_option_choices('ALPHA')

        line_style_options = ['solid', 'dashed', 'dotted', 'dotdash', 'dashdot']

        self.SetSize((500, 580))
        self.text_ctrl_inbox = wx.TextCtrl(self, wx.ID_ANY, "", style=wx.TE_DONTWRAP)
        self.button_inbox = wx.Button(self, wx.ID_ANY, u"…")
        self.text_ctrl_imported = wx.TextCtrl(self, wx.ID_ANY, "", style=wx.TE_DONTWRAP)
        self.button_imported = wx.Button(self, wx.ID_ANY, u"…")
        self.combo_box_colors_category = wx.ComboBox(self, wx.ID_ANY, choices=color_variables,
                                                     style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.combo_box_colors_selection = wx.ComboBox(self, wx.ID_ANY, choices=colors,
                                                      style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.combo_box_sizes_category = wx.ComboBox(self, wx.ID_ANY, choices=size_variables,
                                                    style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.spin_ctrl_sizes_input = wx.SpinCtrl(self, wx.ID_ANY, "0", min=6, max=20, style=wx.SP_ARROW_KEYS)
        self.combo_box_line_widths_category = wx.ComboBox(self, wx.ID_ANY, choices=width_variables,
                                                          style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.spin_ctrl_line_widths_input = wx.SpinCtrl(self, wx.ID_ANY, "0", min=1, max=5, style=wx.SP_ARROW_KEYS)
        self.combo_box_line_styles_category = wx.ComboBox(self, wx.ID_ANY, choices=line_dash_variables,
                                                          style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.combo_box_line_styles_selection = wx.ComboBox(self, wx.ID_ANY, choices=line_style_options,
                                                           style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.combo_box_alpha_category = wx.ComboBox(self, wx.ID_ANY, choices=alpha_variables,
                                                    style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.spin_ctrl_alpha_input = wx.SpinCtrlDouble(self, wx.ID_ANY, "0", min=0.1, max=1.0, style=wx.SP_ARROW_KEYS)
        self.button_restore_defaults = wx.Button(self, wx.ID_ANY, "Restore Defaults")
        self.button_ok = wx.Button(self, wx.ID_OK, "OK")
        self.button_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")

        self.__set_properties()
        self.__do_layout()
        self.__do_bind()

        self.load_options()
        self.load_paths()

        self.Center()

        self.run()

    def __set_properties(self):
        self.text_ctrl_inbox.SetToolTip("Default directory for batch processing of incoming DICOM files")
        self.text_ctrl_inbox.SetMinSize((100, 21))
        self.button_inbox.SetMinSize((40, 21))
        self.text_ctrl_imported.SetToolTip("Directory for post-processed DICOM files")
        self.text_ctrl_imported.SetMinSize((100, 21))
        self.button_imported.SetMinSize((40, 21))
        self.combo_box_colors_category.SetMinSize((250, 25))
        self.combo_box_colors_selection.SetMinSize((145, 25))
        self.combo_box_sizes_category.SetMinSize((250, 25))
        self.spin_ctrl_sizes_input.SetMinSize((50, 22))
        self.combo_box_line_widths_category.SetMinSize((250, 25))
        self.spin_ctrl_line_widths_input.SetMinSize((50, 22))
        self.combo_box_line_styles_category.SetMinSize((250, 25))
        self.combo_box_line_styles_selection.SetMinSize((145, 25))
        self.combo_box_alpha_category.SetMinSize((250, 25))
        self.spin_ctrl_alpha_input.SetMinSize((50, 22))

        self.spin_ctrl_alpha_input.SetIncrement(0.1)

        # Windows needs this done explicitly or the value will be an empty string
        self.combo_box_alpha_category.SetSelection(0)
        self.combo_box_colors_category.SetSelection(0)
        self.combo_box_line_styles_category.SetSelection(0)
        self.combo_box_line_widths_category.SetSelection(0)
        self.combo_box_sizes_category.SetSelection(0)

    def __do_layout(self):
        # begin wxGlade: MyFrame.__do_layout
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_ok_cancel = wx.BoxSizer(wx.HORIZONTAL)
        sizer_plot_options = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Plot Options"), wx.VERTICAL)
        sizer_alpha = wx.BoxSizer(wx.VERTICAL)
        sizer_alpha_input = wx.BoxSizer(wx.HORIZONTAL)
        sizer_line_styles = wx.BoxSizer(wx.VERTICAL)
        sizer_line_styles_input = wx.BoxSizer(wx.HORIZONTAL)
        sizer_line_widths = wx.BoxSizer(wx.VERTICAL)
        sizer_line_widths_input = wx.BoxSizer(wx.HORIZONTAL)
        sizer_sizes = wx.BoxSizer(wx.VERTICAL)
        sizer_sizes_input = wx.BoxSizer(wx.HORIZONTAL)
        sizer_colors = wx.BoxSizer(wx.VERTICAL)
        sizer_colors_input = wx.BoxSizer(wx.HORIZONTAL)
        sizer_dicom_directories = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "DICOM Directories"), wx.VERTICAL)
        sizer_imported_wrapper = wx.BoxSizer(wx.HORIZONTAL)
        sizer_imported = wx.BoxSizer(wx.VERTICAL)
        sizer_imported_input = wx.BoxSizer(wx.HORIZONTAL)
        sizer_inbox_wrapper = wx.BoxSizer(wx.HORIZONTAL)
        sizer_inbox = wx.BoxSizer(wx.VERTICAL)
        sizer_inbox_input = wx.BoxSizer(wx.HORIZONTAL)
        label_inbox = wx.StaticText(self, wx.ID_ANY, "Inbox:")
        label_inbox.SetToolTip("Default directory for batch processing of incoming DICOM files")
        sizer_inbox.Add(label_inbox, 0, 0, 5)
        sizer_inbox_input.Add(self.text_ctrl_inbox, 1, wx.ALL, 5)
        sizer_inbox_input.Add(self.button_inbox, 0, wx.ALL, 5)
        sizer_inbox.Add(sizer_inbox_input, 1, wx.EXPAND, 0)
        sizer_inbox_wrapper.Add(sizer_inbox, 1, wx.EXPAND, 0)
        sizer_dicom_directories.Add(sizer_inbox_wrapper, 1, wx.EXPAND, 0)
        label_imported = wx.StaticText(self, wx.ID_ANY, "Imported:")
        label_imported.SetToolTip("Directory for post-processed DICOM files")
        sizer_imported.Add(label_imported, 0, 0, 5)
        sizer_imported_input.Add(self.text_ctrl_imported, 1, wx.ALL, 5)
        sizer_imported_input.Add(self.button_imported, 0, wx.ALL, 5)
        sizer_imported.Add(sizer_imported_input, 1, wx.EXPAND, 0)
        sizer_imported_wrapper.Add(sizer_imported, 1, wx.EXPAND, 0)
        sizer_dicom_directories.Add(sizer_imported_wrapper, 1, wx.EXPAND, 0)
        sizer_wrapper.Add(sizer_dicom_directories, 0, wx.ALL | wx.EXPAND, 10)
        label_colors = wx.StaticText(self, wx.ID_ANY, "Colors:")
        sizer_colors.Add(label_colors, 0, 0, 0)
        sizer_colors_input.Add(self.combo_box_colors_category, 0, 0, 0)
        sizer_colors_input.Add((20, 20), 0, 0, 0)
        sizer_colors_input.Add(self.combo_box_colors_selection, 0, 0, 0)
        sizer_colors.Add(sizer_colors_input, 1, wx.EXPAND, 0)
        sizer_plot_options.Add(sizer_colors, 1, wx.EXPAND, 0)
        label_sizes = wx.StaticText(self, wx.ID_ANY, "Sizes:")
        sizer_sizes.Add(label_sizes, 0, 0, 0)
        sizer_sizes_input.Add(self.combo_box_sizes_category, 0, 0, 0)
        sizer_sizes_input.Add((20, 20), 0, 0, 0)
        sizer_sizes_input.Add(self.spin_ctrl_sizes_input, 0, 0, 0)
        sizer_sizes.Add(sizer_sizes_input, 1, wx.EXPAND, 0)
        sizer_plot_options.Add(sizer_sizes, 1, wx.EXPAND, 0)
        label_line_widths = wx.StaticText(self, wx.ID_ANY, "Line Widths:")
        sizer_line_widths.Add(label_line_widths, 0, 0, 0)
        sizer_line_widths_input.Add(self.combo_box_line_widths_category, 0, 0, 0)
        sizer_line_widths_input.Add((20, 20), 0, 0, 0)
        sizer_line_widths_input.Add(self.spin_ctrl_line_widths_input, 0, 0, 0)
        sizer_line_widths.Add(sizer_line_widths_input, 1, wx.EXPAND, 0)
        sizer_plot_options.Add(sizer_line_widths, 1, wx.EXPAND, 0)
        label_line_styles = wx.StaticText(self, wx.ID_ANY, "Line Styles:")
        sizer_line_styles.Add(label_line_styles, 0, 0, 0)
        sizer_line_styles_input.Add(self.combo_box_line_styles_category, 0, 0, 0)
        sizer_line_styles_input.Add((20, 20), 0, 0, 0)
        sizer_line_styles_input.Add(self.combo_box_line_styles_selection, 0, 0, 0)
        sizer_line_styles.Add(sizer_line_styles_input, 1, wx.EXPAND, 0)
        sizer_plot_options.Add(sizer_line_styles, 1, wx.EXPAND, 0)
        label_alpha = wx.StaticText(self, wx.ID_ANY, "Alpha:")
        sizer_alpha.Add(label_alpha, 0, 0, 0)
        sizer_alpha_input.Add(self.combo_box_alpha_category, 0, 0, 0)
        sizer_alpha_input.Add((20, 20), 0, 0, 0)
        sizer_alpha_input.Add(self.spin_ctrl_alpha_input, 0, 0, 0)
        sizer_alpha.Add(sizer_alpha_input, 1, wx.EXPAND, 0)
        sizer_plot_options.Add(sizer_alpha, 1, wx.EXPAND, 0)
        sizer_wrapper.Add(sizer_plot_options, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        sizer_ok_cancel.Add(self.button_restore_defaults, 0, wx.RIGHT, 20)
        sizer_ok_cancel.Add(self.button_ok, 0, wx.LEFT | wx.RIGHT, 5)
        sizer_ok_cancel.Add(self.button_cancel, 0, wx.LEFT | wx.RIGHT, 5)
        sizer_wrapper.Add(sizer_ok_cancel, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer_wrapper)
        self.Layout()

    def __do_bind(self):
        self.Bind(wx.EVT_BUTTON, self.inbox_dir_dlg, id=self.button_inbox.GetId())
        self.Bind(wx.EVT_BUTTON, self.imported_dir_dlg, id=self.button_imported.GetId())

        self.Bind(wx.EVT_COMBOBOX, self.update_input_colors_var, id=self.combo_box_colors_category.GetId())
        self.Bind(wx.EVT_COMBOBOX, self.update_size_var, id=self.combo_box_sizes_category.GetId())
        self.Bind(wx.EVT_COMBOBOX, self.update_line_width_var, id=self.combo_box_line_widths_category.GetId())
        self.Bind(wx.EVT_COMBOBOX, self.update_line_style_var, id=self.combo_box_line_styles_category.GetId())
        self.Bind(wx.EVT_COMBOBOX, self.update_alpha_var, id=self.combo_box_alpha_category.GetId())

        self.Bind(wx.EVT_COMBOBOX, self.update_input_colors_val, id=self.combo_box_colors_selection.GetId())
        self.Bind(wx.EVT_TEXT, self.update_size_val, id=self.spin_ctrl_sizes_input.GetId())
        self.Bind(wx.EVT_TEXT, self.update_line_width_val, id=self.spin_ctrl_line_widths_input.GetId())
        self.Bind(wx.EVT_COMBOBOX, self.update_line_style_val, id=self.combo_box_line_styles_selection.GetId())
        self.Bind(wx.EVT_TEXT, self.update_alpha_val, id=self.spin_ctrl_alpha_input.GetId())

        self.Bind(wx.EVT_BUTTON, self.restore_defaults, id=self.button_restore_defaults.GetId())

    def run(self):
        res = self.ShowModal()
        if res == wx.ID_OK:
            self.save_options()
        self.Destroy()

    def inbox_dir_dlg(self, evt):
        starting_dir = self.text_ctrl_inbox.GetValue()
        if not isdir(starting_dir):
            starting_dir = ""
        dlg = wx.DirDialog(self, "Select inbox directory", starting_dir, wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.text_ctrl_inbox.SetValue(dlg.GetPath())
        dlg.Destroy()

    def imported_dir_dlg(self, evt):
        starting_dir = self.text_ctrl_imported.GetValue()
        if not isdir(starting_dir):
            starting_dir = ""
        dlg = wx.DirDialog(self, "Select imported directory", starting_dir, wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.text_ctrl_imported.SetValue(dlg.GetPath())
        dlg.Destroy()

    def get_option_choices(self, category):
        choices = [self.clean_option_variable(c) for c in self.options.option_attr if c.find(category) > -1]
        choices.sort()
        return choices

    @staticmethod
    def clean_option_variable(option_variable, inverse=False):
        if inverse:
            return option_variable.upper().replace(' ', '_')
        else:
            return option_variable.replace('_', ' ').title().replace('Dvh', 'DVH').replace('Iqr', 'IQR')

    def save_options(self):
        self.options.save()

    def update_input_colors_var(self, evt):
        var = self.clean_option_variable(self.combo_box_colors_category.GetValue(), inverse=True)
        val = getattr(self.options, var)
        self.combo_box_colors_selection.SetValue(val)

    def update_input_colors_val(self, evt):
        var = self.clean_option_variable(self.combo_box_colors_category.GetValue(), inverse=True)
        val = self.combo_box_colors_selection.GetValue()
        self.options.set_option(var, val)

    def update_size_var(self, evt):
        var = self.clean_option_variable(self.combo_box_sizes_category.GetValue(), inverse=True)
        try:
            val = getattr(self.options, var).replace('pt', '')
        except AttributeError:
            val = str(getattr(self.options, var))
        try:
            val = int(float(val))
        except ValueError:
            pass
        self.spin_ctrl_sizes_input.SetValue(val)

    def update_size_val(self, evt):
        new = self.spin_ctrl_sizes_input.GetValue()
        if 'Font' in self.combo_box_sizes_category.GetValue():
            try:
                val = str(int(new)) + 'pt'
            except ValueError:
                val = '10pt'
        else:
            try:
                val = float(new)
            except ValueError:
                val = 1.

        var = self.clean_option_variable(self.combo_box_sizes_category.GetValue(), inverse=True)
        self.options.set_option(var, val)

    def update_line_width_var(self, evt):
        var = self.clean_option_variable(self.combo_box_line_widths_category.GetValue(), inverse=True)
        val = str(getattr(self.options, var))
        try:
            val = int(val)
        except ValueError:
            pass
        self.spin_ctrl_line_widths_input.SetValue(val)

    def update_line_width_val(self, evt):
        new = self.spin_ctrl_line_widths_input.GetValue()
        try:
            val = float(new)
        except ValueError:
            val = 1.
        var = self.clean_option_variable(self.combo_box_line_widths_category.GetValue(), inverse=True)
        self.options.set_option(var, val)

    def update_line_style_var(self, evt):
        var = self.clean_option_variable(self.combo_box_line_styles_category.GetValue(), inverse=True)
        self.combo_box_line_styles_selection.SetValue(getattr(self.options, var))

    def update_line_style_val(self, evt):
        var = self.clean_option_variable(self.combo_box_line_styles_category.GetValue(), inverse=True)
        val = self.combo_box_line_styles_selection.GetValue()
        self.options.set_option(var, val)

    def update_alpha_var(self, evt):
        var = self.clean_option_variable(self.combo_box_alpha_category.GetValue(), inverse=True)
        self.spin_ctrl_alpha_input.SetValue(str(getattr(self.options, var)))

    def update_alpha_val(self, evt):
        new = self.spin_ctrl_alpha_input.GetValue()
        try:
            val = float(new)
        except ValueError:
            val = 1.
        var = self.clean_option_variable(self.combo_box_alpha_category.GetValue(), inverse=True)
        self.options.set_option(var, val)

    def load_options(self):
        self.update_alpha_var(None)
        self.update_input_colors_var(None)
        self.update_line_style_var(None)
        self.update_line_width_var(None)
        self.update_size_var(None)

    def load_paths(self):
        paths = parse_settings_file(IMPORT_SETTINGS_PATH)
        self.text_ctrl_inbox.SetValue(paths['inbox'])
        self.text_ctrl_imported.SetValue(paths['imported'])

    def restore_defaults(self, evt):
        MessageDialog(self, "Restore default preferences?", action_yes_func=self.options.restore_defaults)
        self.update_size_val(None)
        self.load_options()