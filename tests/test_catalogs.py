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

from ccesim.catalogs import (
    BUILTIN_CATALOGS,
    CATALOG_DIR_ENV,
    Catalogs,
    default_catalogs,
    reset_default_catalogs,
)


#: Licence families that make crediting the source a condition of use. The
#: loader deliberately never interprets a licence string (see MANIFEST_FIELDS),
#: so this lives here, with the compliance check that needs it.
_ATTRIBUTION_MARKERS = ('cc by', 'creative commons attribution', 'attribution is required')


def _requires_attribution(licence):
    lowered = (licence or '').lower()
    return any(marker in lowered for marker in _ATTRIBUTION_MARKERS)
from ccesim.device import MonitoringDeviceConfig, _resolve_power_type
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


@pytest.fixture(autouse=True)
def clean_catalog_resolution():
    """Resolve the default catalogs from scratch for every test in this module.

    `default_catalogs()` caches, deliberately -- a load test builds thousands
    of devices and must not re-read the files for each. That cache would
    otherwise make the precedence tests depend on which one ran first, and
    would leak whatever CCESIM_CATALOG_DIR the last one set into every other
    test module.
    """
    reset_default_catalogs()
    yield
    reset_default_catalogs()


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
            Catalogs.builtin('kenya-nairobi')
        assert 'kenya-nairobi' in str(excinfo.value)
        assert 'default' in str(excinfo.value)

    def test_the_default_facilities_are_a_small_illustrative_sample(self):
        # The point of the sample: a handful of facilities spanning real
        # climates, rather than a whole registry all in one town.
        assert 6 <= len(facilities) <= 8
        latitudes = [record['latitude'] for record in facilities]
        assert max(latitudes) - min(latitudes) > 25

    def test_the_default_appliances_cover_both_power_types(self):
        assert 4 <= len(fridges) <= 8
        assert {record['power_type'] for record in fridges} == {'solar', 'mains'}

    def test_nigeria_sokoto_restores_the_full_facility_list(self):
        catalogs = Catalogs.builtin('nigeria-sokoto')
        assert len(catalogs.facilities) == 46
        assert catalogs.facilities[0]['facility_name'] == 'Sokoto Hospital Specialist'
        # Only the facilities are replaced; the equipment stays the sample.
        assert len(catalogs.appliances) == len(fridges)
        assert len(catalogs.loggers) == len(rtmds)

    def test_pqs_e003_full_restores_the_full_equipment_lists(self):
        catalogs = Catalogs.builtin('pqs-e003-full')
        assert len(catalogs.appliances) == 96
        assert len(catalogs.loggers) == 13
        assert len(catalogs.facilities) == len(facilities)

    def test_every_appliance_in_the_full_catalog_declares_a_power_type(self):
        for record in Catalogs.builtin('pqs-e003-full').appliances:
            assert record['power_type'] in ('solar', 'mains'), record['APQS']

    def test_the_full_builtins_are_usable_end_to_end(self):
        config = MonitoringDeviceConfig(
            type='rtmd', catalogs=Catalogs.builtin('nigeria-sokoto')
        )
        assert config.facility.state == 'Sokoto'

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

    def test_an_uppercase_extension_is_found(self, tmp_path):
        # Excel and several GIS exporters write .CSV. from_files() already
        # accepts it, and from_dir() used to silently ignore it and hand back
        # the packaged Sokoto facilities while the user believed their own
        # registry had loaded.
        directory = tmp_path / 'shouty'
        directory.mkdir()
        write_csv(directory / 'facilities.CSV', FACILITY_CSV)
        write_json(directory / 'appliances.json', APPLIANCE_ROWS)
        catalogs = Catalogs.from_dir(directory)
        assert [f['facility_name'] for f in catalogs.facilities] == [
            'Sokoto Hospital Specialist', 'Wamakko PHC'
        ]

    def test_an_uppercase_json_extension_is_found(self, tmp_path):
        directory = tmp_path / 'shouty-json'
        directory.mkdir()
        write_json(directory / 'loggers.JSON', LOGGER_ROWS)
        assert len(Catalogs.from_dir(directory).loggers) == 1

    def test_an_uppercase_filename_is_found(self, tmp_path):
        directory = tmp_path / 'shouty-name'
        directory.mkdir()
        write_csv(directory / 'Facilities.Csv', FACILITY_CSV)
        assert len(Catalogs.from_dir(directory).facilities) == 2

    def test_from_dir_and_from_files_agree_on_an_uppercase_extension(self, tmp_path):
        directory = tmp_path / 'agreement'
        directory.mkdir()
        path = write_csv(directory / 'facilities.CSV', FACILITY_CSV)
        assert (Catalogs.from_dir(directory).facilities
                == Catalogs.from_files(facilities=path).facilities)

    def test_two_formats_differing_only_in_extension_case_are_ambiguous(self, tmp_path):
        directory = tmp_path / 'case-ambiguous'
        directory.mkdir()
        write_csv(directory / 'facilities.csv', FACILITY_CSV)
        write_json(directory / 'facilities.JSON', FACILITY_ROWS)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(directory)
        message = str(excinfo.value)
        assert 'facilities.csv' in message
        assert 'facilities.JSON' in message

    def test_two_files_differing_only_in_name_case_are_ambiguous(self, tmp_path):
        directory = tmp_path / 'name-ambiguous'
        directory.mkdir()
        write_csv(directory / 'facilities.csv', FACILITY_CSV)
        write_csv(directory / 'Facilities.csv', FACILITY_CSV)
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(directory)
        assert 'keep only one' in str(excinfo.value)

    def test_an_unsupported_extension_in_the_directory_is_ignored(self, tmp_path):
        # A README or a spreadsheet left beside the catalogs must not be
        # mistaken for one, nor stop the packaged fallback.
        directory = tmp_path / 'with-clutter'
        directory.mkdir()
        (directory / 'facilities.xlsx').write_text('not a catalog', encoding='utf-8')
        write_json(directory / 'appliances.json', APPLIANCE_ROWS)
        catalogs = Catalogs.from_dir(directory)
        assert len(catalogs.facilities) == len(facilities)
        assert len(catalogs.appliances) == 2


class TestProvenanceManifest:
    """A catalog can say where it came from; it never has to.

    The manifest exists so that a shared facility list carries its own terms,
    and so that nobody has to guess whether the packaged sample is real
    registry data. Both halves are pinned here: what a manifest must report,
    and that its absence is completely silent.
    """

    def test_a_directory_without_a_manifest_loads_silently(self, csv_dir, caplog):
        with caplog.at_level(logging.DEBUG):
            catalogs = Catalogs.from_dir(csv_dir)
        assert catalogs.manifest == {}
        assert caplog.records == []

    def test_a_manifest_is_read_and_exposed(self, csv_dir):
        (csv_dir / 'manifest.json').write_text(json.dumps({
            'facilities': {
                'source': 'Kenya Master Health Facility List',
                'vintage': '2025 Q1',
                'licence': 'CC BY 4.0',
                'url': 'https://example.gov/mfl',
                'retrieved': '2025-03-14',
            },
        }), encoding='utf-8')
        catalogs = Catalogs.from_dir(csv_dir)
        assert catalogs.manifest['facilities']['source'] == (
            'Kenya Master Health Facility List'
        )
        assert catalogs.manifest['facilities']['retrieved'] == '2025-03-14'

    def test_manifest_fields_are_free_form(self, csv_dir):
        # No controlled vocabulary: a country's own terms must survive.
        (csv_dir / 'manifest.json').write_text(json.dumps({
            'loggers': {'source': 'MoH procurement export',
                        'contact': 'coldchain@example.gov'},
        }), encoding='utf-8')
        catalogs = Catalogs.from_dir(csv_dir)
        assert catalogs.manifest['loggers']['contact'] == 'coldchain@example.gov'

    def test_an_uppercase_manifest_filename_is_found(self, csv_dir):
        (csv_dir / 'Manifest.json').write_text(
            json.dumps({'facilities': {'source': 'HFR export'}}), encoding='utf-8'
        )
        catalogs = Catalogs.from_dir(csv_dir)
        assert catalogs.manifest['facilities']['source'] == 'HFR export'

    def test_a_manifest_for_a_catalog_that_is_not_there_is_an_error(self, tmp_path):
        # Otherwise the packaged default appliances would be labelled with
        # someone else's provenance.
        directory = tmp_path / 'facilities-only'
        directory.mkdir()
        write_csv(directory / 'facilities.csv', FACILITY_CSV)
        (directory / 'manifest.json').write_text(
            json.dumps({'appliances': {'source': 'Our own fridges'}}),
            encoding='utf-8',
        )
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(directory)
        assert 'appliances' in str(excinfo.value)
        assert 'manifest.json' in str(excinfo.value)

    def test_a_manifest_key_that_is_not_a_catalog_kind_is_an_error(self, csv_dir):
        (csv_dir / 'manifest.json').write_text(
            json.dumps({'source': 'flat, not keyed by kind'}), encoding='utf-8'
        )
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(csv_dir)
        assert 'facilities' in str(excinfo.value)

    def test_a_malformed_manifest_names_the_file(self, csv_dir):
        (csv_dir / 'manifest.json').write_text('{ not json', encoding='utf-8')
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(csv_dir)
        assert 'manifest.json' in str(excinfo.value)

    def test_a_manifest_entry_must_be_an_object(self, csv_dir):
        (csv_dir / 'manifest.json').write_text(
            json.dumps({'facilities': 'NHFR'}), encoding='utf-8'
        )
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_dir(csv_dir)
        assert 'facilities' in str(excinfo.value)

    def test_a_replaced_catalog_keeps_the_packaged_provenance(self, tmp_path):
        # from_dir() with only facilities leaves the packaged equipment in
        # place, so the manifest must still describe where that came from.
        directory = tmp_path / 'facilities-only'
        directory.mkdir()
        write_csv(directory / 'facilities.csv', FACILITY_CSV)
        catalogs = Catalogs.from_dir(directory)
        assert 'facilities' not in catalogs.manifest
        assert 'E003' in catalogs.manifest['appliances']['source']
        assert 'E006' in catalogs.manifest['loggers']['source']

    def test_the_packaged_default_reports_synthetic_facilities(self):
        # The sample facilities are invented. Labelling them NHFR/GRID3 would
        # restore the confusion that shrinking the default set removed.
        manifest = Catalogs().manifest
        source = manifest['facilities']['source']
        assert 'Synthetic' in source
        assert 'NHFR' not in source
        assert 'GRID3' not in source
        assert manifest['facilities']['licence']

    def test_nigeria_sokoto_reports_the_grid3_provenance(self):
        manifest = Catalogs.builtin('nigeria-sokoto').manifest
        assert 'GRID3 NGA - Health Facilities v2.0' in manifest['facilities']['source']
        # Its equipment is still the packaged sample, and says so.
        assert 'E003' in manifest['appliances']['source']

    def test_an_attribution_licence_is_matched_by_a_citation(self):
        # Not a claim about any one dataset: attribution licences (CC BY and
        # friends) make crediting the source a CONDITION of redistribution, so
        # a licence that demands it and a manifest that cannot supply it puts
        # the package out of compliance. Applies to every catalog we ship, and
        # to any a country or manufacturer drops in.
        for name in BUILTIN_CATALOGS:
            for kind, entry in Catalogs.builtin(name).manifest.items():
                licence = entry.get('licence', '')
                if not _requires_attribution(licence):
                    continue
                citation = entry.get('citation', '').strip()
                assert citation, (
                    f"builtin {name!r} {kind} is licensed under terms requiring "
                    f"attribution ({licence[:40]}...) but carries no citation"
                )

    def test_pqs_e003_full_reports_the_who_catalogue(self):
        manifest = Catalogs.builtin('pqs-e003-full').manifest
        assert 'E003' in manifest['appliances']['source']
        assert 'E006' in manifest['loggers']['source']
        # Its facilities are still the synthetic sample, and say so.
        assert 'Synthetic' in manifest['facilities']['source']

    def test_records_in_hand_carry_no_provenance(self):
        # Lists passed straight to Catalogs() are the caller's; the loader has
        # nothing to say about them and must not invent anything.
        catalogs = Catalogs(facilities=FACILITY_ROWS)
        assert 'facilities' not in catalogs.manifest

    def test_a_manifest_may_be_passed_directly(self):
        catalogs = Catalogs(
            facilities=FACILITY_ROWS,
            manifest={'facilities': {'source': 'Our own export'}},
        )
        assert catalogs.manifest['facilities']['source'] == 'Our own export'

    def test_a_manifest_for_an_unsupplied_catalog_is_an_error(self):
        with pytest.raises(ValueError) as excinfo:
            Catalogs(facilities=FACILITY_ROWS,
                     manifest={'loggers': {'source': 'Ours'}})
        assert 'loggers' in str(excinfo.value)

    def test_the_manifest_does_not_alias_the_packaged_literal(self):
        catalogs = Catalogs()
        catalogs.manifest['facilities']['source'] = 'mutated'
        assert 'Synthetic' in Catalogs().manifest['facilities']['source']

    def test_a_manifest_leaves_the_records_alone(self, csv_dir):
        (csv_dir / 'manifest.json').write_text(
            json.dumps({'facilities': {'source': 'HFR export'}}), encoding='utf-8'
        )
        with_manifest = Catalogs.from_dir(csv_dir)
        (csv_dir / 'manifest.json').unlink()
        without = Catalogs.from_dir(csv_dir)
        assert with_manifest.facilities == without.facilities
        assert with_manifest.appliances == without.appliances


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

    def test_a_repeated_column_name_is_an_error(self, tmp_path):
        # csv.DictReader collapses same-named columns to the LAST value, so
        # this used to load with latitude = 14.99: a plausible wrong number
        # reaching the ambient and solar model instead of an error.
        path = write_csv(tmp_path / 'facilities.csv', """
iso,latitude,latitude,longitude
NGA,13.06,14.99,5.25
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        message = str(excinfo.value)
        assert 'facilities.csv' in message
        assert 'latitude' in message

    def test_a_repeated_column_is_rejected_before_any_row_is_read(self, tmp_path):
        # The header alone is enough; a file with no data rows must still fail
        # rather than report the catalog as merely empty.
        path = write_csv(tmp_path / 'facilities.csv', """
iso,latitude,latitude,longitude
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'latitude' in str(excinfo.value)

    def test_a_repeated_column_differing_only_in_case_is_an_error(self, tmp_path):
        path = write_csv(tmp_path / 'facilities.csv', """
iso,latitude,Latitude,longitude
NGA,13.06,14.99,5.25
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        message = str(excinfo.value)
        assert 'latitude' in message and 'Latitude' in message

    def test_a_repeated_column_the_loader_does_not_recognize_is_an_error(self, tmp_path):
        # A duplicated join column is just as much a sign of a broken export,
        # and silently keeping the second value is just as wrong.
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude,openlmis_id,openlmis_id
Sokoto Hospital Specialist,NGA,13.06,5.25,OLMIS-42,OLMIS-43
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'openlmis_id' in str(excinfo.value)

    def test_trailing_empty_columns_load_and_are_dropped(self, tmp_path):
        # The classic Excel 'Save as CSV' artefact: a sheet where someone once
        # typed in a far column exports with trailing commas on every line.
        # Those cells carry no data and are dropped as "not stated", so two or
        # more of them must not read as a column named '' appearing twice.
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude,,
Sokoto Hospital Specialist,NGA,13.06,5.25,,
""")
        record = Catalogs.from_files(facilities=path).facilities[0]
        assert record == {
            'facility_name': 'Sokoto Hospital Specialist',
            'iso': 'NGA',
            'latitude': pytest.approx(13.06),
            'longitude': pytest.approx(5.25),
        }

    def test_one_trailing_empty_column_still_loads(self, tmp_path):
        # The single-comma case always loaded; it must stay consistent with the
        # two-comma one rather than the two diverging.
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude,
Sokoto Hospital Specialist,NGA,13.06,5.25,
""")
        assert list(Catalogs.from_files(facilities=path).facilities[0]) == [
            'facility_name', 'iso', 'latitude', 'longitude',
        ]

    def test_a_named_duplicate_beside_empty_columns_is_still_an_error(self, tmp_path):
        # Tolerating the unnamed columns must not blunt the real check.
        path = write_csv(tmp_path / 'facilities.csv', """
iso,latitude,latitude,longitude,,
NGA,13.06,14.99,5.25,,
""")
        with pytest.raises(ValueError) as excinfo:
            Catalogs.from_files(facilities=path)
        assert 'latitude' in str(excinfo.value)

    def test_distinct_columns_that_merely_look_alike_still_load(self, tmp_path):
        # Guards the duplicate check against over-reach: 'lga' and 'lga_name'
        # are different columns and must both survive.
        path = write_csv(tmp_path / 'facilities.csv', """
facility_name,iso,latitude,longitude,lga,lga_name_disagreement
Sokoto Hospital Specialist,NGA,13.06,5.25,Sokoto South,0
""")
        record = Catalogs.from_files(facilities=path).facilities[0]
        assert record['lga'] == 'Sokoto South'
        assert record['lga_name_disagreement'] == '0'

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


# ===========================================================================
# Resolution order: explicit catalogs= > CCESIM_CATALOG_DIR > packaged default
# ===========================================================================

CATALOG_FACILITY_NAMES = {'Sokoto Hospital Specialist', 'Wamakko PHC'}
CATALOG_APPLIANCE_CODES = {'E003/007', 'E003/030'}


class TestDefaultCatalogResolution:
    """`default_catalogs()` is the whole zero-code story, so pin its order."""

    def test_the_packaged_default_when_nothing_is_set(self, monkeypatch):
        monkeypatch.delenv(CATALOG_DIR_ENV, raising=False)
        assert len(default_catalogs().facilities) == len(facilities)

    def test_the_environment_variable_is_used_when_set(self, monkeypatch, csv_dir):
        monkeypatch.setenv(CATALOG_DIR_ENV, str(csv_dir))
        catalogs = default_catalogs()
        assert {f['facility_name'] for f in catalogs.facilities} == CATALOG_FACILITY_NAMES
        assert {a['APQS'] for a in catalogs.appliances} == CATALOG_APPLIANCE_CODES

    def test_an_empty_environment_variable_means_unset(self, monkeypatch):
        monkeypatch.setenv(CATALOG_DIR_ENV, '')
        assert len(default_catalogs().facilities) == len(facilities)

    def test_a_missing_directory_fails_loudly(self, monkeypatch, tmp_path):
        # The one thing this must never do is fall back to the packaged example
        # facilities, which would silently simulate the wrong country.
        monkeypatch.setenv(CATALOG_DIR_ENV, str(tmp_path / 'no-such-catalog'))
        with pytest.raises(ValueError) as excinfo:
            default_catalogs()
        message = str(excinfo.value)
        assert CATALOG_DIR_ENV in message
        assert 'no-such-catalog' in message

    def test_an_empty_directory_fails_loudly(self, monkeypatch, tmp_path):
        directory = tmp_path / 'nothing-in-here'
        directory.mkdir()
        monkeypatch.setenv(CATALOG_DIR_ENV, str(directory))
        with pytest.raises(ValueError) as excinfo:
            default_catalogs()
        assert 'no catalog files' in str(excinfo.value)

    def test_a_broken_catalog_file_fails_loudly(self, monkeypatch, tmp_path):
        directory = tmp_path / 'broken'
        directory.mkdir()
        write_csv(directory / 'facilities.csv', """
facility_name,iso,latitude,longitude
Wamakko PHC,NGA,,5.11
""")
        monkeypatch.setenv(CATALOG_DIR_ENV, str(directory))
        with pytest.raises(ValueError) as excinfo:
            default_catalogs()
        assert 'latitude' in str(excinfo.value)

    def test_the_files_are_read_once_and_cached(self, monkeypatch, csv_dir, json_dir):
        monkeypatch.setenv(CATALOG_DIR_ENV, str(csv_dir))
        first = default_catalogs()
        assert default_catalogs() is first
        # Changing the environment does not reach into the cache: a load test
        # building thousands of devices must not re-read the files.
        monkeypatch.setenv(CATALOG_DIR_ENV, str(json_dir))
        assert default_catalogs() is first

    def test_resetting_makes_the_next_call_re_read(self, monkeypatch, csv_dir):
        monkeypatch.delenv(CATALOG_DIR_ENV, raising=False)
        assert len(default_catalogs().facilities) == len(facilities)
        monkeypatch.setenv(CATALOG_DIR_ENV, str(csv_dir))
        reset_default_catalogs()
        assert len(default_catalogs().facilities) == 2


class TestMonitoringDeviceConfigCatalogs:
    """The three call sites in MonitoringDeviceConfig, at each ceremony level."""

    def test_an_explicit_catalogs_object_is_used(self, monkeypatch, csv_dir):
        monkeypatch.delenv(CATALOG_DIR_ENV, raising=False)
        config = MonitoringDeviceConfig(type='rtmd', catalogs=Catalogs.from_dir(csv_dir))
        assert config.facility.facility_name in CATALOG_FACILITY_NAMES
        assert config.appliance.pqs_code in CATALOG_APPLIANCE_CODES
        assert config.device.model == 'SmartLine'

    def test_the_environment_variable_needs_no_code_change(self, monkeypatch, csv_dir):
        # This is the locustfile.py / notebook path: MonitoringDeviceConfig is
        # constructed exactly as it is today, with nothing passed.
        monkeypatch.setenv(CATALOG_DIR_ENV, str(csv_dir))
        config = MonitoringDeviceConfig(type='rtmd')
        assert config.facility.facility_name in CATALOG_FACILITY_NAMES
        assert config.device.model == 'SmartLine'

    def test_an_explicit_catalogs_object_beats_the_environment_variable(
        self, monkeypatch, csv_dir, json_dir
    ):
        monkeypatch.setenv(CATALOG_DIR_ENV, str(json_dir))
        only = Catalogs(
            facilities=[dict(FACILITY_ROWS[0], facility_name='Argued For')],
            appliances=APPLIANCE_ROWS,
            loggers=LOGGER_ROWS,
        )
        config = MonitoringDeviceConfig(type='ems', catalogs=only)
        assert config.facility.facility_name == 'Argued For'

    def test_the_packaged_default_when_neither_is_given(self, monkeypatch):
        monkeypatch.delenv(CATALOG_DIR_ENV, raising=False)
        config = MonitoringDeviceConfig(type='ems')
        assert len(config.catalogs.facilities) == len(facilities)
        assert len(config.catalogs.appliances) == len(fridges)

    def test_an_unusable_environment_variable_reaches_the_caller(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(CATALOG_DIR_ENV, str(tmp_path / 'absent'))
        with pytest.raises(ValueError) as excinfo:
            MonitoringDeviceConfig(type='ems')
        assert CATALOG_DIR_ENV in str(excinfo.value)

    def test_an_explicit_facility_still_wins_over_the_catalog(self, monkeypatch, csv_dir):
        # Passing one specific facility stays a distinct, useful thing.
        monkeypatch.delenv(CATALOG_DIR_ENV, raising=False)
        chosen = Facility({'facility_name': 'Chosen PHC', 'iso': 'KEN',
                           'latitude': -1.28, 'longitude': 36.82})
        config = MonitoringDeviceConfig(
            type='ems', facility=chosen, catalogs=Catalogs.from_dir(csv_dir)
        )
        assert config.facility is chosen
        assert config.appliance.pqs_code in CATALOG_APPLIANCE_CODES

    def test_manufacturer_still_filters_within_the_catalog(self, monkeypatch, csv_dir):
        monkeypatch.delenv(CATALOG_DIR_ENV, raising=False)
        config = MonitoringDeviceConfig(
            type='rtmd', manufacturer='Berlinger',
            catalogs=Catalogs.from_dir(csv_dir),
        )
        assert config.device.manufacturer == 'Berlinger & Co. AG'

    def test_every_device_shares_one_resolved_catalog(self, monkeypatch, csv_dir):
        monkeypatch.setenv(CATALOG_DIR_ENV, str(csv_dir))
        first = MonitoringDeviceConfig(type='ems')
        second = MonitoringDeviceConfig(type='rtmd')
        assert first.catalogs is second.catalogs

    def test_a_path_passed_as_catalogs_is_refused(self, csv_dir):
        with pytest.raises(TypeError) as excinfo:
            MonitoringDeviceConfig(type='ems', catalogs=str(csv_dir))
        assert 'Catalogs' in str(excinfo.value)
