'''
Cross-implementation parity: both ports read the same catalog directory.

The point of the documented catalog format is that a country writes ONE catalog
and both implementations agree on what they read. This test enforces that on
`js/fixtures/catalog/`, the shared parity fixture: it loads the directory with
`ccesim.catalogs.Catalogs.from_dir()`, loads the SAME directory with the
JavaScript port's `fromDir()` by running node, and compares the two results.

NEITHER SIDE HOLDS AN EXPECTED ANSWER. The comparison is always between two live
loads, so there is no snapshot to update: changing a key-normalization rule in
one port only turns this red, and it cannot be made green by editing a literal
here. `js/src/cross-validation.test.js` runs the same comparison from the other
direction, so a one-sided change is caught by either suite on its own.

The fixture records are deliberately awkward -- alias spellings, spreadsheet
headers, coordinates written as strings, unrecognized columns -- because that is
where the two ports could drift. See `js/fixtures/catalog/README.md` for what
each record exercises.
'''

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ccesim.catalogs import CATALOG_KINDS, Catalogs

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The catalog directory both ports load. Shared, not copied: a fixture each
#: port kept its own copy of could drift and still pass.
FIXTURE_DIR = REPO_ROOT / 'js' / 'fixtures' / 'catalog'

#: The JS port's Node-only loader, reached by absolute path so this test does
#: not depend on the package being installed or linked.
CATALOGS_NODE = REPO_ROOT / 'js' / 'src' / 'catalogs-node.js'

#: Read the fixture with the JS port and print the loaded records as JSON. The
#: paths arrive through the environment, so the script itself stays a constant.
_JS_DIGEST_SCRIPT = '''
const { fromDir } = await import(process.env.CCESIM_JS_CATALOGS_NODE);
const catalogs = fromDir(process.env.CCESIM_CATALOG_DIR);
const digest = {};
for (const kind of ["facilities", "appliances", "loggers"]) {
  digest[kind] = catalogs.records(kind);
}
process.stdout.write(JSON.stringify(digest));
'''

#: The facility fields the simulator actually reads off a catalog record.
FACILITY_FIELDS = ('iso', 'latitude', 'longitude', 'facility_name')

#: The fields that identify a piece of equipment, in the stored PQS-style form.
APPLIANCE_FIELDS = ('APQS', 'AMFR', 'AMOD', 'type', 'power_type')
LOGGER_FIELDS = ('LPQS', 'LMFR', 'LMOD', 'type')

COMPARED_FIELDS = {
    'facilities': FACILITY_FIELDS,
    'appliances': APPLIANCE_FIELDS,
    'loggers': LOGGER_FIELDS,
}


def _records(catalogs):
    '''The loaded records of each kind, as plain JSON-comparable data.'''
    return {kind: getattr(catalogs, kind) for kind in CATALOG_KINDS}


@pytest.fixture(scope='module')
def python_records():
    '''The fixture catalog as the Python loader sees it.'''
    return _records(Catalogs.from_dir(FIXTURE_DIR))


@pytest.fixture(scope='module')
def js_records():
    '''The same catalog as the JavaScript loader sees it.'''
    node = shutil.which('node')
    if node is None:
        pytest.skip(
            'node is not installed, so the JavaScript half of the catalog '
            'parity comparison cannot run'
        )
    completed = subprocess.run(
        [node, '--input-type=module', '-e', _JS_DIGEST_SCRIPT],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            'CCESIM_JS_CATALOGS_NODE': CATALOGS_NODE.as_uri(),
            'CCESIM_CATALOG_DIR': str(FIXTURE_DIR),
        },
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"the JavaScript port failed to load {FIXTURE_DIR}:\n"
            f"{completed.stderr.strip()}"
        )
    return json.loads(completed.stdout)


def _counts(records):
    return {kind: len(records[kind]) for kind in CATALOG_KINDS}


def _key_sets(records):
    return [sorted(record) for record in records]


def _fields(records, fields):
    return [{field: record.get(field) for field in fields} for record in records]


def test_both_ports_load_the_same_number_of_records(python_records, js_records):
    assert _counts(js_records) == _counts(python_records)
    # Guard against a comparison trivially satisfied by two empty loads.
    assert all(count > 0 for count in _counts(python_records).values())


@pytest.mark.parametrize('kind', CATALOG_KINDS)
def test_normalized_key_sets_match_record_for_record(
    kind, python_records, js_records
):
    '''
    Every accepted spelling must resolve to the same stored key in both ports.
    This is the assertion that fails when a normalization rule is changed on one
    side only.
    '''
    assert _key_sets(js_records[kind]) == _key_sets(python_records[kind])


@pytest.mark.parametrize('kind', CATALOG_KINDS)
def test_the_fields_the_simulator_reads_match(kind, python_records, js_records):
    '''
    The facility fields the thermal and solar models read, and the fields that
    identify a piece of equipment. Values, not just key names: a coordinate that
    stays a string in one port is a divergence too.
    '''
    fields = COMPARED_FIELDS[kind]
    assert _fields(js_records[kind], fields) == _fields(
        python_records[kind], fields
    )


def test_coordinates_are_numbers_in_both_ports(python_records, js_records):
    '''
    Both ports coerce a coordinate written as a string. Equality alone would not
    catch both ports leaving it a string, which reaches the models as nonsense.
    '''
    for records in (python_records['facilities'], js_records['facilities']):
        for record in records:
            assert isinstance(record['latitude'], float)
            assert isinstance(record['longitude'], float)


@pytest.mark.parametrize('kind', CATALOG_KINDS)
def test_every_normalized_record_matches(kind, python_records, js_records):
    '''
    The catch-all: unrecognized keys ride along untouched in both ports, and any
    field either port keeps that the comparisons above do not name is still
    covered.
    '''
    assert js_records[kind] == python_records[kind]


@pytest.mark.parametrize('kind', CATALOG_KINDS)
def test_the_fixture_still_exercises_normalization(kind, python_records):
    '''
    Parity over a fixture written entirely in stored-form keys would prove
    nothing, so check the fixture still uses spellings that have to be
    normalized before the comparisons above mean anything.
    '''
    written = json.loads((FIXTURE_DIR / f'{kind}.json').read_text(encoding='utf-8'))
    written_keys = {key for record in written for key in record}
    loaded_keys = {key for record in python_records[kind] for key in record}
    assert written_keys - loaded_keys, (
        f"{kind}.json no longer uses any alias spelling, so parity over it no "
        f"longer tests key normalization"
    )
