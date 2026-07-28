"""Tests for the pluggable catalog loader.

The point of `ccesim.catalogs` is that a country can bring its own facility
registry export and its own equipment list, in whatever format and field naming
it already has, and have the simulator either load it or say precisely which
file and row is wrong. These tests pin both halves of that: what must load, and
what must fail loudly rather than reach the thermal model as a None.
"""

import json
import logging

import pytest

from ccesim.catalogs import Catalogs
from ccesim.device import _resolve_power_type
from ccesim.devicegroups import (
    Device,
    DeviceGroup,
    device_manufacturer,
    fridges,
    rtmds,
)
from ccesim.facilities import Facility, facilities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FACILITY_ROWS = [
    {
        "facility_name": "Sokoto Hospital Specialist",
        "iso": "NGA",
        "state": "Sokoto",
        "latitude": 13.0622968415,
        "longitude": 5.25763348855,
    },
    {
        "facility_name": "Wamakko PHC",
        "iso": "NGA",
        "state": "Sokoto",
        "latitude": 13.0021,
        "longitude": 5.1102,
    },
]

APPLIANCE_ROWS = [
    {
        "APQS": "E003/007",
        "type": "Icelined refrigerator",
        "AMFR": "Vestfrost Solutions",
        "AMOD": "MK 304",
        "power_type": "mains",
    },
    {
        "APQS": "E003/030",
        "type": "Solar direct drive refrigerator",
        "AMFR": "B Medical Systems Sarl",
        "AMOD": "TCW 3000 SDD",
        "power_type": "solar",
    },
]

LOGGER_ROWS = [
    {
        "LPQS": "E006/019",
        "type": "Remote Temperature Monitoring Device",
        "LMFR": "Berlinger & Co. AG",
        "LMOD": "SmartLine",
    },
]


def write_json(path, rows):
    path.write_text(json.dumps(rows), encoding='utf-8')
    return path


def write_csv(path, text):
    """Write CSV from a literal block, so the fixture reads like a spreadsheet."""
    path.write_text(text.strip() + "\n", encoding='utf-8')
    return path


FACILITY_CSV = """
facility_name,iso,state,latitude,longitude
Sokoto Hospital Specialist,NGA,Sokoto,13.0622968415,5.25763348855
Wamakko PHC,NGA,Sokoto,13.0021,5.1102
"""

APPLIANCE_CSV = """
APQS,type,AMFR,AMOD,power_type
E003/007,Icelined refrigerator,Vestfrost Solutions,MK 304,mains
E003/030,Solar direct drive refrigerator,B Medical Systems Sarl,TCW 3000 SDD,solar
"""

LOGGER_CSV = """
LPQS,type,LMFR,LMOD
E006/019,Remote Temperature Monitoring Device,Berlinger & Co. AG,SmartLine
"""


@pytest.fixture
def json_dir(tmp_path):
    directory = tmp_path / 'json-catalog'
    directory.mkdir()
    write_json(directory / 'facilities.json', FACILITY_ROWS)
    write_json(directory / 'appliances.json', APPLIANCE_ROWS)
    write_json(directory / 'loggers.json', LOGGER_ROWS)
    return directory


@pytest.fixture
def csv_dir(tmp_path):
    directory = tmp_path / 'csv-catalog'
    directory.mkdir()
    write_csv(directory / 'facilities.csv', FACILITY_CSV)
    write_csv(directory / 'appliances.csv', APPLIANCE_CSV)
    write_csv(directory / 'loggers.csv', LOGGER_CSV)
    return directory


# ===========================================================================
# The packaged defaults
# ===========================================================================

class TestBuiltinCatalogs:

    def test_bare_constructor_loads_the_packaged_catalogs(self):
        catalogs = Catalogs()
        assert len(catalogs.facilities) == len(facilities)
        assert len(catalogs.appliances) == len(fridges)
        assert len(catalogs.loggers) == len(rtmds)

    def test_builtin_default_matches_the_bare_constructor(self):
        assert len(Catalogs.builtin('default').appliances) == len(fridges)

    def test_builtin_name_defaults_to_default(self):
        assert len(Catalogs.builtin().loggers) == len(rtmds)

    def test_unknown_builtin_name_is_rejected(self):
        with pytest.raises(ValueError) as excinfo:
            Catalogs.builtin('nigeria-sokoto')
        assert 'nigeria-sokoto' in str(excinfo.value)
        assert 'default' in str(excinfo.value)

    def test_the_packaged_literals_are_not_mutated(self):
        before = [dict(record) for record in fridges]
        Catalogs()
        assert fridges == before

    def test_loading_copies_rather_than_aliases_the_packaged_records(self):
        catalogs = Catalogs()
        assert catalogs.appliances[0] == fridges[0]
        assert catalogs.appliances[0] is not fridges[0]

    def test_the_packaged_facilities_survive_validation(self):
        # Every shipped facility must already satisfy the minimum schema; if it
        # does not, users get an error on a catalog they never touched.
        for record in Catalogs().facilities:
            assert isinstance(record['latitude'], float)
            assert isinstance(record['longitude'], float)
            assert record['iso']


# ===========================================================================
# Loading from files
# ===========================================================================

class TestFromDir:

    def test_a_json_directory_loads(self, json_dir):
        catalogs = Catalogs.from_dir(json_dir)
        assert len(catalogs.facilities) == 2
        assert len(catalogs.appliances) == 2
        assert len(catalogs.loggers) == 1

    def test_a_csv_directory_loads(self, csv_dir):
        catalogs = Catalogs.from_dir(csv_dir)
        assert len(catalogs.facilities) == 2
        assert len(catalogs.appliances) == 2
        assert len(catalogs.loggers) == 1

    def test_json_and_csv_directories_agree(self, json_dir, csv_dir):
        assert Catalogs.from_dir(csv_dir).facilities == Catalogs.from_dir(json_dir).facilities
        assert Catalogs.from_dir(csv_dir).appliances == Catalogs.from_dir(json_dir).appliances

    def test_a_missing_catalog_falls_back_to_the_packaged_default(self, tmp_path):
        directory = tmp_path / 'facilities-only'
        directory.mkdir()
        write_json(directory / 'facilities.json', FACILITY_ROWS)
        catalogs = Catalogs.from_dir(directory)
        assert len(catalogs.facilities) == 2
        assert len(catalogs.appliances) == len(fridges)
        assert len(catalogs.loggers) == len(rtmds)

    def test_mixed_formats_in_one_directory(self, tmp_path):
        directory = tmp_path / 'mixed'
        directory.mkdir()
        write_csv(directory / 'facilities.csv', FACILITY_CSV)
        write_json(directory / 'appliances.json', APPLIANCE_ROWS)
        catalogs = Catalogs.from_dir(directory)
        assert len(catalogs.facilities) == 2
        assert len(catalogs.appliances) == 2

    def test_both_formats_for_one_catalog_is_ambiguous(self, tmp_path):
        directory = tmp_path / 'ambiguous'
        directory.mkdir()
        write_json(directory / 'appliances.json', APPLIANCE_ROWS)
        write_csv(directory / 'appliances.csv', APPLIANCE_CSV)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(directory)
        assert 'appliances.json' in str(excinfo.value)
        assert 'appliances.csv' in str(excinfo.value)

    def test_a_directory_with_no_catalog_files_is_an_error(self, tmp_path):
        directory = tmp_path / 'empty'
        directory.mkdir()
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(directory)
        assert 'no catalog files' in str(excinfo.value)

    def test_a_missing_directory_is_an_error(self, tmp_path):
        with pytest.raises(ValueError):
            Catalogs.from_dir(tmp_path / 'nope')


class TestFromFiles:

    def test_a_csv_facility_list_beside_a_json_appliance_list(self, tmp_path):
        catalogs = Catalogs.from_files(
            facilities=write_csv(tmp_path / 'hfr_export.csv', FACILITY_CSV),
            appliances=write_json(tmp_path / 'our_fridges.json', APPLIANCE_ROWS),
        )
        assert [f['facility_name'] for f in catalogs.facilities] == [
            'Sokoto Hospital Specialist', 'Wamakko PHC'
        ]
        assert len(catalogs.appliances) == 2
        # Not supplied, so the packaged loggers stay.
        assert len(catalogs.loggers) == len(rtmds)

    def test_no_arguments_is_an_error(self):
        with pytest.raises(ValueError):
            Catalogs.from_files()

    def test_a_missing_file_names_the_path(self, tmp_path):
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=tmp_path / 'absent.csv')
        assert 'absent.csv' in str(excinfo.value)

    def test_an_unsupported_extension_is_rejected(self, tmp_path):
        path = tmp_path / 'facilities.xlsx'
        path.write_text('not really a spreadsheet', encoding='utf-8')
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert '.xlsx' in str(excinfo.value)

    def test_malformed_json_names_the_file(self, tmp_path):
        path = tmp_path / 'appliances.json'
        path.write_text('[{"APQS": ', encoding='utf-8')
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        assert 'appliances.json' in str(excinfo.value)

    def test_json_must_be_an_array(self, tmp_path):
        path = write_json(tmp_path / 'appliances.json', {'appliances': APPLIANCE_ROWS})
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        assert 'array' in str(excinfo.value)

    def test_an_empty_catalog_file_is_an_error(self, tmp_path):
        path = write_json(tmp_path / 'appliances.json', [])
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        assert 'empty' in str(excinfo.value)


# ===========================================================================
# Key normalization
# ===========================================================================

class TestKeyNormalization:
    """PQS-style and plain field names must both drop straight in."""

    def test_plain_appliance_keys_are_accepted(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator,mains
""")
        record = Catalogs.from_files(appliances=path).appliances[0]
        assert record['APQS'] == 'E003/007'
        assert record['AMFR'] == 'Vestfrost Solutions'
        assert record['AMOD'] == 'MK 304'

    def test_plain_logger_keys_are_accepted(self, tmp_path):
        path = write_csv(tmp_path / 'loggers.csv', """
pqs_code,manufacturer,model,type
E006/019,Berlinger & Co. AG,SmartLine,Remote Temperature Monitoring Device
""")
        record = Catalogs.from_files(loggers=path).loggers[0]
        assert record['LPQS'] == 'E006/019'
        assert record['LMFR'] == 'Berlinger & Co. AG'
        assert record['LMOD'] == 'SmartLine'

    def test_pqs_keyed_and_plain_keyed_inputs_produce_the_same_record(self, tmp_path):
        pqs = write_csv(tmp_path / 'a.csv', """
APQS,AMFR,AMOD,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator,mains
""")
        plain = write_csv(tmp_path / 'b.csv', """
pqs_code,manufacturer,model,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator,mains
""")
        assert (Catalogs.from_files(appliances=pqs).appliances
                == Catalogs.from_files(appliances=plain).appliances)

    def test_spreadsheet_style_headers_are_accepted(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
Facility Name,ISO,Lat,Long
Sokoto Hospital Specialist,NGA,13.06,5.25
""")
        record = Catalogs.from_files(facilities=path).facilities[0]
        assert record['facility_name'] == 'Sokoto Hospital Specialist'
        assert record['iso'] == 'NGA'
        assert record['latitude'] == pytest.approx(13.06)
        assert record['longitude'] == pytest.approx(5.25)

    def test_unrecognized_columns_ride_along_untouched(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude,openlmis_id,Our Ref
Sokoto Hospital Specialist,NGA,13.06,5.25,OLMIS-42,ref/7
""")
        record = Catalogs.from_files(facilities=path).facilities[0]
        assert record['openlmis_id'] == 'OLMIS-42'
        assert record['Our Ref'] == 'ref/7'

    def test_two_columns_meaning_the_same_field_is_an_error(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
APQS,pqs_code,manufacturer,model,type
E003/007,E003/008,Vestfrost Solutions,MK 304,Icelined refrigerator
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        message = str(excinfo.value)
        assert 'APQS' in message and 'pqs_code' in message

    def test_a_byte_order_mark_does_not_corrupt_the_first_column(self, tmp_path):
        path = tmp_path / 'facilities.csv'
        path.write_text(FACILITY_CSV.strip() + "\n", encoding='utf-8-sig')
        assert Catalogs.from_files(facilities=path).facilities[0]['facility_name']

    def test_a_facility_row_is_still_a_valid_facility(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', FACILITY_CSV)
        facility = Facility(Catalogs.from_files(facilities=path).facilities[0])
        assert facility.facility_name == 'Sokoto Hospital Specialist'
        assert facility.iso == 'NGA'
        assert facility.latitude == pytest.approx(13.0622968415)


# ===========================================================================
# Validation
# ===========================================================================

class TestRequiredFields:
    """A missing required field must fail at load, naming file and row."""

    def test_a_missing_latitude_names_the_file_and_the_row(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude
Sokoto Hospital Specialist,NGA,13.06,5.25
Wamakko PHC,NGA,,5.11
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        message = str(excinfo.value)
        assert 'facilities.csv' in message
        assert 'latitude' in message
        assert 'line 3' in message

    def test_a_missing_latitude_in_json_names_the_record(self, tmp_path):
        rows = [dict(FACILITY_ROWS[0]), dict(FACILITY_ROWS[1])]
        del rows[1]['latitude']
        path = write_json(tmp_path / 'facilities.json', rows)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        message = str(excinfo.value)
        assert 'facilities.json' in message
        assert 'record 2' in message
        assert 'latitude' in message

    def test_a_missing_iso_is_an_error(self, tmp_path):
        rows = [{k: v for k, v in FACILITY_ROWS[0].items() if k != 'iso'}]
        path = write_json(tmp_path / 'facilities.json', rows)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'iso' in str(excinfo.value)

    def test_a_missing_appliance_model_is_an_error(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type
E003/007,Vestfrost Solutions,,Icelined refrigerator
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        message = str(excinfo.value)
        assert 'AMOD' in message
        assert 'model' in message

    def test_a_missing_logger_type_is_an_error(self, tmp_path):
        rows = [{k: v for k, v in LOGGER_ROWS[0].items() if k != 'type'}]
        path = write_json(tmp_path / 'loggers.json', rows)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(loggers=path)
        assert 'type' in str(excinfo.value)

    def test_an_appliance_list_loaded_as_loggers_fails_loudly(self, tmp_path):
        path = write_json(tmp_path / 'loggers.json', APPLIANCE_ROWS)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(loggers=path)
        assert 'LPQS' in str(excinfo.value)


class TestCoordinates:
    """Coordinates reach the thermal model, so they must be numbers."""

    def test_csv_coordinates_become_floats(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', FACILITY_CSV)
        record = Catalogs.from_files(facilities=path).facilities[0]
        assert isinstance(record['latitude'], float)
        assert isinstance(record['longitude'], float)

    def test_a_non_numeric_latitude_is_rejected(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude
Sokoto Hospital Specialist,NGA,13°03'N,5.25
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'not a number' in str(excinfo.value)

    def test_an_out_of_range_latitude_is_rejected(self, tmp_path):
        # A dropped decimal point is the classic registry export defect.
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude
Sokoto Hospital Specialist,NGA,1306.22,5.25
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'outside' in str(excinfo.value)

    def test_longitude_may_exceed_ninety(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude
Kathmandu Central,NPL,27.7172,85.3240
""")
        record = Catalogs.from_files(facilities=path).facilities[0]
        assert record['longitude'] == pytest.approx(85.324)


class TestPowerType:
    """The explicit power_type from ccesim-q25.3, arriving through a file."""

    def test_declared_power_type_is_normalized(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator, MAINS
""")
        assert Catalogs.from_files(appliances=path).appliances[0]['power_type'] == 'mains'

    def test_an_invalid_power_type_names_the_file_row_and_appliance(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator,diesel
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        message = str(excinfo.value)
        assert 'appliances.csv' in message
        assert 'line 2' in message
        assert 'diesel' in message
        assert 'E003/007' in message

    def test_a_blank_power_type_cell_means_absent_not_invalid(self, tmp_path):
        # A user fills the column in only for the appliances they care about.
        # That must load, with the blank rows falling back to the type sniff --
        # not fail on a row they intentionally left empty.
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator,mains
E003/999,Acme Cold Chain Ltd,PV-100,Refrigerator (photovoltaic),solar
E003/030,B Medical Systems Sarl,TCW 3000 SDD,Solar direct drive refrigerator,
E003/024,Vestfrost Solutions,MF 114,Vaccine/Waterpacks freezer,
""")
        appliances = Catalogs.from_files(appliances=path).appliances
        assert [record.get('power_type') for record in appliances] == [
            'mains', 'solar', None, None,
        ]
        # The blank rows are absent, not empty strings, so the resolver sniffs.
        assert _resolve_power_type(Device.from_dict(appliances[2])) == 'solar'
        assert _resolve_power_type(Device.from_dict(appliances[3])) == 'mains'

    def test_a_whitespace_only_power_type_cell_means_absent(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type,power_type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator,"   "
""")
        assert 'power_type' not in Catalogs.from_files(appliances=path).appliances[0]

    def test_a_blank_power_type_still_takes_the_sniff_path_end_to_end(self, tmp_path, caplog):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type,power_type
E003/030,B Medical Systems Sarl,TCW 3000 SDD,Solar direct drive refrigerator,
""")
        appliance = Device.from_dict(Catalogs.from_files(appliances=path).appliances[0])
        with caplog.at_level(logging.INFO, logger='ccesim.device'):
            _resolve_power_type(appliance)
        assert any('declares no power_type' in r.getMessage() for r in caplog.records)

    def test_an_explicitly_empty_power_type_in_json_is_still_loud(self, tmp_path):
        # JSON has a real null for "not stated", so an empty string there is a
        # mistake worth reporting rather than a blank spreadsheet cell.
        rows = [dict(APPLIANCE_ROWS[0], power_type='')]
        path = write_json(tmp_path / 'appliances.json', rows)
        with pytest.raises(ValueError):
            Catalogs.from_files(appliances=path)

    def test_a_json_null_power_type_means_absent(self, tmp_path):
        rows = [dict(APPLIANCE_ROWS[0], power_type=None)]
        path = write_json(tmp_path / 'appliances.json', rows)
        assert Catalogs.from_files(appliances=path).appliances[0]['power_type'] is None


class TestMalformedRows:

    def test_a_row_with_more_values_than_columns_is_an_error(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude
Sokoto Hospital Specialist,NGA,13.06,5.25,surprise
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'more values' in str(excinfo.value)

    def test_a_headerless_empty_csv_is_an_error(self, tmp_path):
        path = tmp_path / 'facilities.csv'
        path.write_text('', encoding='utf-8')
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'header' in str(excinfo.value)

    def test_a_json_array_of_non_objects_is_an_error(self, tmp_path):
        path = write_json(tmp_path / 'appliances.json', ['E003/007'])
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(appliances=path)
        assert 'record 1' in str(excinfo.value)


# ===========================================================================
# Lists of dicts in hand
# ===========================================================================

class TestInMemoryCatalogs:

    def test_lists_of_dicts_are_accepted(self):
        catalogs = Catalogs(
            facilities=FACILITY_ROWS,
            appliances=APPLIANCE_ROWS,
            loggers=LOGGER_ROWS,
        )
        assert len(catalogs.facilities) == 2
        assert catalogs.appliances[1]['power_type'] == 'solar'

    def test_the_input_dicts_are_not_mutated(self):
        rows = [dict(APPLIANCE_ROWS[0], power_type='MAINS')]
        Catalogs(appliances=rows)
        assert rows[0]['power_type'] == 'MAINS'

    def test_an_invalid_in_memory_record_still_names_the_row(self):
        rows = [dict(APPLIANCE_ROWS[0]), dict(APPLIANCE_ROWS[1], power_type='diesel')]
        with pytest.raises(ValueError) as excinfo:
            Catalogs(appliances=rows)
        assert 'record 2' in str(excinfo.value)

    def test_a_path_passed_to_the_constructor_is_refused(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', FACILITY_CSV)
        with pytest.raises(TypeError) as excinfo:
            Catalogs(facilities=str(path))
        assert 'from_files' in str(excinfo.value)

    def test_an_empty_list_is_an_error(self):
        with pytest.raises(ValueError) as excinfo:
            Catalogs(appliances=[])
        assert 'empty' in str(excinfo.value)


# ===========================================================================
# The loaded records feed the existing consumers
# ===========================================================================

class TestConsumers:
    """A loaded catalog must be usable exactly where the literals are today."""

    def test_loaded_appliances_drive_a_device_group(self, csv_dir):
        group = DeviceGroup(Catalogs.from_dir(csv_dir).appliances)
        device = group.random_device()
        assert device.pqs_code in ('E003/007', 'E003/030')
        assert device.power_type in ('mains', 'solar')

    def test_loaded_loggers_drive_a_device_group(self, csv_dir):
        group = DeviceGroup(Catalogs.from_dir(csv_dir).loggers)
        assert group.random_device().model == 'SmartLine'

    def test_plain_keyed_input_still_produces_a_usable_device(self, tmp_path):
        path = write_csv(tmp_path / 'appliances.csv', """
pqs_code,manufacturer,model,type
E003/007,Vestfrost Solutions,MK 304,Icelined refrigerator
""")
        device = Device.from_dict(Catalogs.from_files(appliances=path).appliances[0])
        assert device.manufacturer == 'Vestfrost Solutions'
        assert device.model == 'MK 304'

    def test_grouping_by_manufacturer_survives_a_mixed_list(self):
        # The retired _resolve_manufacturer_key decided the key from the first
        # record alone, so a list mixing appliance and logger records grouped
        # everything under whichever style came first.
        group = DeviceGroup([dict(APPLIANCE_ROWS[0]), dict(LOGGER_ROWS[0])])
        assert set(group.group_by_manufacturer()) == {
            'Vestfrost Solutions', 'Berlinger & Co. AG',
        }

    def test_device_manufacturer_reads_either_key_style(self):
        assert device_manufacturer(APPLIANCE_ROWS[0]) == 'Vestfrost Solutions'
        assert device_manufacturer(LOGGER_ROWS[0]) == 'Berlinger & Co. AG'

    def test_device_manufacturer_rejects_a_record_with_neither(self):
        with pytest.raises(ValueError):
            device_manufacturer({'APQS': 'E003/007'})
