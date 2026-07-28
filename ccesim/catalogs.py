'''
Pluggable facility and equipment catalogs.

The simulator draws a facility, an appliance and a logger from three catalogs.
This module lets those catalogs come from files a user supplies -- a country's
own facility registry export, the equipment actually deployed there, a
manufacturer's own product line -- instead of only from the literals packaged
in `ccesim.facilities` and `ccesim.devicegroups`.

    Catalogs()                                       # the packaged defaults
    Catalogs(facilities=[...], appliances=[...])     # lists of dicts in hand
    Catalogs.from_dir('./ke-catalog')                # facilities/appliances/loggers.{json,csv}
    Catalogs.from_files(facilities='hfr_export.csv', appliances='fridges.json')
    Catalogs.builtin('default')                      # a named packaged catalog

Anything not supplied falls back to the packaged default, so a country that
only has its own facility list keeps the packaged PQS equipment catalogs.

BOTH JSON AND CSV ARE ACCEPTED. JSON is an array of objects, matching the shape
of the packaged literals. CSV is what a country program actually has, because
the facility list comes out of an HFR or OpenLMIS as a spreadsheet.

KEYS ARE NORMALIZED ON LOAD. An unmodified WHO PQS export uses APQS/AMFR/AMOD
for appliances and LPQS/LMFR/LMOD for loggers; a country's own list is far more
likely to say pqs_code/manufacturer/model. Both are accepted, along with case
and spacing variants, and are stored in the PQS-style form the rest of the
package already reads. Keys that are not recognized ride along untouched, so a
user keeps their own join columns.

VALIDATION IS LOUD AND HAPPENS AT LOAD. A facility with no latitude must fail
here, naming the file and the row, rather than reaching the thermal model as a
None and producing silent nonsense.
'''

import csv
import json
from pathlib import Path
from typing import NamedTuple

from ccesim.devicegroups import (
    device_label,
    validate_power_type,
    fridges as _DEFAULT_APPLIANCES,
    rtmds as _DEFAULT_LOGGERS,
)
from ccesim.facilities import facilities as _DEFAULT_FACILITIES

#: The three catalogs a Catalogs object carries.
CATALOG_KINDS = ('facilities', 'appliances', 'loggers')

#: Named packaged catalogs resolvable through `Catalogs.builtin()`.
BUILTIN_CATALOGS = ('default',)

#: Catalog file formats understood by `from_dir()` and `from_files()`.
CATALOG_SUFFIXES = ('.json', '.csv')


# ---------------------------------------------------------------------------
# Key normalization
# ---------------------------------------------------------------------------

def _normalize_key(key):
    '''Fold a source column name to the form the alias tables are keyed on.'''
    return str(key).strip().lower().replace(' ', '_').replace('-', '_')


#: The keys `ccesim.facilities.Facility` reads, verbatim. Listed here so that an
#: unmodified NHFR-style export keeps every column, whatever its case or
#: spacing. Keep in step with `Facility.__init__`.
_FACILITY_NATIVE_KEYS = (
    'OBJECTID', 'globalid', 'nhfr_uid', 'nhfr_facility_code', 'country', 'iso',
    'state', 'lga', 'lga_name_disagreement', 'ward', 'ward_name_disagreement',
    'facility_name', 'facility_name_source', 'ownership', 'ownership_type',
    'facility_level', 'facility_level_option', 'latitude', 'longitude',
    'geocoordinates_source', 'last_updated',
)

FACILITY_ALIASES = {_normalize_key(key): key for key in _FACILITY_NATIVE_KEYS}
FACILITY_ALIASES.update({
    'lat': 'latitude',
    'lon': 'longitude',
    'lng': 'longitude',
    'long': 'longitude',
    'name': 'facility_name',
    'facility': 'facility_name',
    'iso3': 'iso',
    'iso_code': 'iso',
    'country_code': 'iso',
    'facility_code': 'nhfr_facility_code',
})

APPLIANCE_ALIASES = {
    'apqs': 'APQS',
    'pqs': 'APQS',
    'pqs_code': 'APQS',
    'amfr': 'AMFR',
    'manufacturer': 'AMFR',
    'amod': 'AMOD',
    'model': 'AMOD',
    'type': 'type',
    'appliance_type': 'type',
    'power_type': 'power_type',
    'powertype': 'power_type',
    'power_source': 'power_type',
}

LOGGER_ALIASES = {
    'lpqs': 'LPQS',
    'pqs': 'LPQS',
    'pqs_code': 'LPQS',
    'lmfr': 'LMFR',
    'manufacturer': 'LMFR',
    'lmod': 'LMOD',
    'model': 'LMOD',
    'type': 'type',
    'logger_type': 'type',
    'device_type': 'type',
}

#: Minimum required fields per kind, as (stored key, the plain equivalent an
#: error message should also mention).
REQUIRED_FIELDS = {
    'facilities': (('iso', 'iso'), ('latitude', 'lat'), ('longitude', 'lon')),
    'appliances': (
        ('APQS', 'pqs_code'), ('AMFR', 'manufacturer'),
        ('AMOD', 'model'), ('type', 'type'),
    ),
    'loggers': (
        ('LPQS', 'pqs_code'), ('LMFR', 'manufacturer'),
        ('LMOD', 'model'), ('type', 'type'),
    ),
}

#: Singular noun per kind, for error messages.
_RECORD_NOUN = {
    'facilities': 'facility',
    'appliances': 'appliance',
    'loggers': 'logger',
}


def _normalize_record(record, aliases, location):
    '''
    Rename a record's recognized keys to their stored form, leaving everything
    else exactly as the user wrote it.
    '''
    normalized = {}
    origin = {}
    for key, value in record.items():
        if key is None:
            # csv.DictReader parks surplus values under a None key.
            raise ValueError(
                f"{location}: row has more values than the header has columns"
            )
        stored = aliases.get(_normalize_key(key), key)
        if stored in origin and origin[stored] != key:
            raise ValueError(
                f"{location}: {origin[stored]!r} and {key!r} both mean "
                f"{stored!r}; keep only one of them"
            )
        normalized[stored] = value
        origin[stored] = key
    return normalized


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _require_fields(record, kind, location):
    noun = _RECORD_NOUN[kind]
    for stored, plain in REQUIRED_FIELDS[kind]:
        value = record.get(stored)
        if value is None or (isinstance(value, str) and not value.strip()):
            also = '' if plain == stored else f" (also accepted as {plain!r})"
            raise ValueError(
                f"{location}: {noun} record is missing required field "
                f"{stored!r}{also}"
            )


def _coerce_coordinate(record, field, limit, location):
    '''
    Turn a coordinate into a float and sanity-check its range. CSV hands over
    every cell as a string, and a latitude that stays a string -- or that lost
    its decimal point -- reaches the ambient and solar models as nonsense.
    '''
    value = record[field]
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{location}: facility {field} {value!r} is not a number"
        ) from None
    if not -limit <= coordinate <= limit:
        raise ValueError(
            f"{location}: facility {field} {coordinate} is outside "
            f"{-limit}..{limit}"
        )
    record[field] = coordinate


def _validate_facility(record, location):
    _require_fields(record, 'facilities', location)
    _coerce_coordinate(record, 'latitude', 90, location)
    _coerce_coordinate(record, 'longitude', 180, location)


def _validate_appliance(record, location):
    _require_fields(record, 'appliances', location)
    if 'power_type' in record:
        try:
            record['power_type'] = validate_power_type(
                record['power_type'], device_label(record)
            )
        except ValueError as exc:
            raise ValueError(f"{location}: {exc}") from None


def _validate_logger(record, location):
    _require_fields(record, 'loggers', location)


_KIND_HANDLERS = {
    'facilities': (FACILITY_ALIASES, _validate_facility),
    'appliances': (APPLIANCE_ALIASES, _validate_appliance),
    'loggers': (LOGGER_ALIASES, _validate_logger),
}


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

class _Loaded(NamedTuple):
    '''Raw records read from a file, each paired with where it came from.'''
    source: str
    pairs: list


def _read_json(path, kind):
    with open(path, encoding='utf-8') as handle:
        try:
            payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: not valid JSON: {exc}") from None
    if not isinstance(payload, list):
        raise ValueError(
            f"{path}: expected a JSON array of {kind} records, got "
            f"{type(payload).__name__}"
        )
    pairs = []
    for index, record in enumerate(payload, start=1):
        location = f"{path} record {index}"
        if not isinstance(record, dict):
            raise ValueError(
                f"{location}: expected an object, got {type(record).__name__}"
            )
        pairs.append((location, record))
    return pairs


def _clean_csv_row(row, location):
    '''
    Trim a CSV row and drop its blank cells.

    A blank cell means "not stated", not "the empty string". Dropping it is
    what lets a column that is only filled in for some rows -- power_type on a
    catalog where the user only cared about a handful of appliances -- load at
    all, while a blank cell in a *required* column still fails the missing
    field check below.
    '''
    cleaned = {}
    for key, value in row.items():
        if key is None:
            raise ValueError(
                f"{location}: row has more values than the header has columns"
            )
        if value is None:
            # csv.DictReader pads a short row with None.
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        cleaned[key] = value
    return cleaned


def _reject_duplicate_columns(path, fieldnames):
    '''
    Refuse a header row that names the same column twice.

    `csv.DictReader` collapses same-named columns to the LAST value with no
    warning, so a header duplicated by a hand-edit or a sloppy join would
    otherwise put a plausible wrong number -- the second latitude cell --
    into the ambient and solar model. The check has to run on the raw header
    row, because by the time a row is a dict the evidence is gone.

    Case and spacing are folded, so 'latitude' and 'Latitude' count as the
    same column here rather than falling through to the synonym check below.
    '''
    seen = {}
    for name in fieldnames:
        folded = _normalize_key(name)
        if folded in seen:
            first = seen[folded]
            clash = (
                f"column {name!r} appears more than once"
                if first == name
                else f"columns {first!r} and {name!r} are the same column"
            )
            raise ValueError(f"{path}: {clash}; keep only one of them")
        seen[folded] = name


def _read_csv(path, kind):
    pairs = []
    # utf-8-sig so a byte-order mark from Excel does not become part of the
    # first column name.
    with open(path, newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: file is empty; expected a header row")
        _reject_duplicate_columns(path, reader.fieldnames)
        for row in reader:
            location = f"{path} line {reader.line_num}"
            pairs.append((location, _clean_csv_row(row, location)))
    return pairs


def _read_path(path, kind):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"{path}: no such {kind} catalog file")
    suffix = path.suffix.lower()
    if suffix == '.json':
        pairs = _read_json(path, kind)
    elif suffix == '.csv':
        pairs = _read_csv(path, kind)
    else:
        raise ValueError(
            f"{path}: unsupported catalog format {path.suffix!r}; expected "
            f"{' or '.join(CATALOG_SUFFIXES)}"
        )
    return _Loaded(str(path), pairs)


# ---------------------------------------------------------------------------
# Catalogs
# ---------------------------------------------------------------------------

_BUILTIN_RECORDS = {
    'default': {
        'facilities': _DEFAULT_FACILITIES,
        'appliances': _DEFAULT_APPLIANCES,
        'loggers': _DEFAULT_LOGGERS,
    },
}


def _prepare(loaded, kind):
    '''Normalize and validate every record of one catalog.'''
    aliases, validate = _KIND_HANDLERS[kind]
    records = []
    for location, raw in loaded.pairs:
        record = _normalize_record(raw, aliases, location)
        validate(record, location)
        records.append(record)
    if not records:
        raise ValueError(f"{loaded.source}: {kind} catalog is empty")
    return records


def _as_loaded(records, kind):
    '''Accept None (packaged default), a list of dicts, or an already-read file.'''
    if records is None:
        source = f"builtin catalog 'default' ({kind})"
        records = _BUILTIN_RECORDS['default'][kind]
    elif isinstance(records, _Loaded):
        return records
    else:
        source = f"{kind} passed to Catalogs()"
    if isinstance(records, (str, Path)) or not isinstance(records, (list, tuple)):
        raise TypeError(
            f"{kind} must be a list of dicts; use Catalogs.from_files() to "
            f"load them from a path"
        )
    pairs = []
    for index, record in enumerate(records, start=1):
        location = f"{source} record {index}"
        if not isinstance(record, dict):
            raise TypeError(
                f"{location}: expected a dict, got {type(record).__name__}"
            )
        pairs.append((location, record))
    return _Loaded(source, pairs)


class Catalogs:
    '''
    The three catalogs the simulator draws from: facilities, appliances and
    loggers.

    Each argument is a list of dicts; anything left out falls back to the
    packaged default. Records are normalized and validated on the way in, so a
    Catalogs object that exists is one every consumer can read without
    re-checking. The lists are copies -- loading never mutates the dicts handed
    in, nor the packaged literals.
    '''

    def __init__(self, facilities=None, appliances=None, loggers=None):
        self.facilities = _prepare(_as_loaded(facilities, 'facilities'), 'facilities')
        self.appliances = _prepare(_as_loaded(appliances, 'appliances'), 'appliances')
        self.loggers = _prepare(_as_loaded(loggers, 'loggers'), 'loggers')

    @classmethod
    def builtin(cls, name='default'):
        '''Load a named catalog packaged with the simulator.'''
        if name not in BUILTIN_CATALOGS:
            raise ValueError(
                f"Unknown builtin catalog {name!r}: expected one of "
                f"{', '.join(repr(n) for n in BUILTIN_CATALOGS)}"
            )
        return cls()

    @classmethod
    def from_dir(cls, path):
        '''
        Load `facilities`, `appliances` and `loggers` from a directory, each as
        either .json or .csv. A catalog with no file in the directory falls
        back to the packaged default.

        Names are matched case-insensitively, so the `facilities.CSV` that
        Excel and several GIS exporters produce is found here exactly as
        `from_files()` already accepts it. Two files that both claim the same
        catalog -- `facilities.csv` beside `facilities.JSON`, or beside
        `Facilities.csv` -- is an error rather than a resolution by luck.
        '''
        directory = Path(path)
        if not directory.is_dir():
            raise ValueError(f"{directory}: not a catalog directory")
        candidates = sorted(
            (entry for entry in directory.iterdir() if entry.is_file()),
            key=lambda entry: entry.name,
        )
        found = {}
        for kind in CATALOG_KINDS:
            matches = [
                entry for entry in candidates
                if entry.stem.lower() == kind
                and entry.suffix.lower() in CATALOG_SUFFIXES
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"{directory}: found more than one {kind} catalog file ("
                    + ', '.join(entry.name for entry in matches)
                    + "); keep only one"
                )
            if matches:
                found[kind] = _read_path(matches[0], kind)
        if not found:
            raise ValueError(
                f"{directory}: no catalog files found; expected any of "
                + ', '.join(
                    f"{kind}{suffix}"
                    for kind in CATALOG_KINDS for suffix in CATALOG_SUFFIXES
                )
            )
        return cls(**found)

    @classmethod
    def from_files(cls, facilities=None, appliances=None, loggers=None):
        '''
        Load catalogs from individual files, in any mix of formats. Anything
        not given falls back to the packaged default.
        '''
        given = {
            kind: path
            for kind, path in (
                ('facilities', facilities),
                ('appliances', appliances),
                ('loggers', loggers),
            )
            if path is not None
        }
        if not given:
            raise ValueError(
                "from_files() needs at least one of facilities=, appliances= "
                "or loggers="
            )
        return cls(**{
            kind: _read_path(path, kind) for kind, path in given.items()
        })

    def __repr__(self):
        return (
            f"Catalogs(facilities={len(self.facilities)}, "
            f"appliances={len(self.appliances)}, loggers={len(self.loggers)})"
        )
