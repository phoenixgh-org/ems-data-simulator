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
    Catalogs.builtin('nigeria-sokoto')                # a named packaged catalog

Anything not supplied falls back to the packaged default, so a country that
only has its own facility list keeps the packaged PQS equipment catalogs.

THE PACKAGED DEFAULT IS A SAMPLE, NOT A REFERENCE DATASET: seven synthetic
facilities spanning subtropical to equatorial latitudes, six appliances and
three loggers, sized to demonstrate the simulator rather than to describe any
country's real estate. The full sets it used to ship are still here as named
builtins -- `'nigeria-sokoto'` for the 46 real Sokoto State facilities and
`'pqs-e003-full'` for the whole prequalified equipment catalogue.

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

A CATALOG MAY CARRY ITS PROVENANCE. A `manifest.json` beside the catalog files
records where each catalog came from -- source, vintage, licence, url,
retrieved -- and is exposed as `Catalogs.manifest`. It is optional: a catalog
without one loads exactly as before, silently, because most third-party
catalogs will not have one. The packaged catalogs carry theirs here in code,
since they are literals rather than files. See `MANIFEST_FILENAME` below for
the shape.
'''

import csv
import json
import os
from pathlib import Path
from typing import NamedTuple

from ccesim.devicegroups import (
    device_label,
    validate_power_type,
    fridges as _DEFAULT_APPLIANCES,
    rtmds as _DEFAULT_LOGGERS,
    pqs_e003_fridges as _PQS_APPLIANCES,
    pqs_e006_rtmds as _PQS_LOGGERS,
)
from ccesim.facilities import (
    facilities as _DEFAULT_FACILITIES,
    nigeria_sokoto_facilities as _SOKOTO_FACILITIES,
)

#: The three catalogs a Catalogs object carries.
CATALOG_KINDS = ('facilities', 'appliances', 'loggers')

#: Catalog file formats understood by `from_dir()` and `from_files()`.
CATALOG_SUFFIXES = ('.json', '.csv')

#: Environment variable naming a catalog directory to use when no `Catalogs`
#: was passed explicitly. This is what makes the feature zero-code: it works
#: for `locustfile.py`, the notebook and any downstream script unchanged.
CATALOG_DIR_ENV = 'CCESIM_CATALOG_DIR'

#: Optional provenance file, read by `from_dir()` from beside the catalog
#: files. A JSON object keyed by catalog kind, each entry free-form:
#:
#:     {
#:       "facilities": {
#:         "source": "Kenya Master Health Facility List",
#:         "vintage": "2025 Q1",
#:         "licence": "CC BY 4.0",
#:         "url": "https://example.gov/mfl",
#:         "retrieved": "2025-03-14"
#:       }
#:     }
#:
#: Per kind rather than per directory because provenance genuinely differs
#: between them -- a country brings its own facility list but keeps the
#: packaged WHO PQS equipment catalogs.
MANIFEST_FILENAME = 'manifest.json'

#: The provenance fields this project uses. A CONVENTION, NOT A SCHEMA: the
#: loader neither requires these nor rejects others, and never interprets a
#: value. A licence here is a string a human reads, not a controlled term.
MANIFEST_FIELDS = ('source', 'vintage', 'licence', 'url', 'retrieved')


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

    UNNAMED COLUMNS ARE NOT COLUMNS. A header ending in two or more commas is
    the classic Excel 'Save as CSV' artefact from a sheet where someone once
    typed in a far column; every such cell is blank and `_clean_csv_row()`
    already drops it as "not stated". Counting them here as a column named ''
    duplicated would reject a file that carries no duplicate data at all, and
    with a message naming no column the user could find.
    '''
    seen = {}
    for name in fieldnames:
        folded = _normalize_key(name)
        if not folded:
            continue
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
# Provenance manifests
# ---------------------------------------------------------------------------

def _validated_manifest(manifest, location):
    '''
    Check a manifest's SHAPE -- keyed by catalog kind, each entry an object --
    and copy it. The fields inside an entry are never inspected: they are for
    a human, and a country that wants to record its own extra terms should be
    able to.
    '''
    if not isinstance(manifest, dict):
        raise TypeError(
            f"{location}: manifest must be an object keyed by catalog kind "
            f"({', '.join(CATALOG_KINDS)}), got {type(manifest).__name__}"
        )
    validated = {}
    for kind, entry in manifest.items():
        if kind not in CATALOG_KINDS:
            raise ValueError(
                f"{location}: {kind!r} is not a catalog kind; a manifest is "
                f"keyed by {', '.join(CATALOG_KINDS)}, and each of those holds "
                f"the provenance fields ({', '.join(MANIFEST_FIELDS)})"
            )
        if not isinstance(entry, dict):
            raise ValueError(
                f"{location}: {kind!r} provenance must be an object of fields, "
                f"got {type(entry).__name__}"
            )
        validated[kind] = dict(entry)
    return validated


def _read_manifest(path):
    with open(path, encoding='utf-8') as handle:
        try:
            payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: not valid JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise ValueError(
            f"{path}: expected a JSON object keyed by catalog kind, got "
            f"{type(payload).__name__}"
        )
    return _validated_manifest(payload, str(path))


# ---------------------------------------------------------------------------
# Catalogs
# ---------------------------------------------------------------------------

#: The named packaged catalogs. 'default' is the small illustrative sample the
#: simulator falls back to; the others are the full sets it used to ship as
#: that default, kept opt-in. A builtin names only the catalogs it replaces --
#: everything else falls back to the default, so 'nigeria-sokoto' is the real
#: Sokoto facility list against the sample equipment, not a second copy of it.
_BUILTIN_RECORDS = {
    'default': {
        'facilities': _DEFAULT_FACILITIES,
        'appliances': _DEFAULT_APPLIANCES,
        'loggers': _DEFAULT_LOGGERS,
    },
    'nigeria-sokoto': {
        'facilities': _SOKOTO_FACILITIES,
    },
    'pqs-e003-full': {
        'appliances': _PQS_APPLIANCES,
        'loggers': _PQS_LOGGERS,
    },
}

#: Named packaged catalogs resolvable through `Catalogs.builtin()`.
BUILTIN_CATALOGS = tuple(_BUILTIN_RECORDS)

#: Provenance for the packaged catalogs. They are Python literals rather than
#: files, so their manifest lives here instead of in a `manifest.json`.
#:
#: THE DEFAULT FACILITIES ARE SYNTHETIC and their provenance says so. The real
#: registry records are 'nigeria-sokoto' and nowhere else -- describing the
#: sample as NHFR/GRID3 data would restore exactly the confusion that shrinking
#: the default set removed.
#:
#: A field whose value is not actually known is left out rather than guessed:
#: an unverified licence string is worse than none, because a reader would act
#: on it.
_BUILTIN_MANIFESTS = {
    'default': {
        'facilities': {
            'source': (
                'Synthetic. Invented "Example ..." facilities placed at real, '
                'plausible cold chain coordinates from 27N to 26S; no real '
                'health facility is named. Recorded per record as '
                'facility_name_source / geocoordinates_source = '
                'SYNTHETIC_EXAMPLE.'
            ),
            'vintage': '2026',
            'licence': 'MIT, as part of this package',
            'url': 'https://github.com/phoenixgh-org/ems-data-simulator',
        },
        'appliances': {
            'source': (
                'Six appliances sampled from the WHO PQS prequalified '
                'equipment catalogue (E003), chosen to cover the power and '
                'thermal archetypes the simulator models'
            ),
            'licence': 'Public WHO catalogue',
        },
        'loggers': {
            'source': (
                'Three remote temperature monitoring devices sampled from the '
                'WHO PQS prequalified equipment catalogue (E006)'
            ),
            'licence': 'Public WHO catalogue',
        },
    },
    'nigeria-sokoto': {
        'facilities': {
            'source': (
                'Nigeria Health Facility Registry (NHFR) for facility names, '
                'GRID3 eHealth for coordinates; recorded per record as '
                'facility_name_source=NHFR_2024 and '
                'geocoordinates_source=GRID3_EHEALTH'
            ),
            'vintage': 'NHFR 2024',
            'licence': (
                'Both are public datasets; redistribution terms have not been '
                'confirmed for this package'
            ),
        },
    },
    'pqs-e003-full': {
        'appliances': {
            'source': (
                'WHO PQS prequalified equipment catalogue, E003 refrigerators '
                'and freezers, in full'
            ),
            'licence': 'Public WHO catalogue',
        },
        'loggers': {
            'source': (
                'WHO PQS prequalified equipment catalogue, E006 remote '
                'temperature monitoring devices, in full'
            ),
            'licence': 'Public WHO catalogue',
        },
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


def _resolve_manifest(manifest, supplied):
    '''
    Work out the provenance of each of the three catalogs this object ends up
    holding.

    A kind that fell back to the packaged default gets the PACKAGED
    provenance, not the caller's -- so `from_dir()` on a directory holding only
    facilities still reports the WHO PQS origin of the appliances it did not
    replace. A kind that has no provenance at all is simply absent from the
    result, which is the normal case for a third-party catalog.
    '''
    location = 'manifest passed to Catalogs()'
    given = _validated_manifest(manifest, location) if manifest is not None else {}
    resolved = {}
    for kind in CATALOG_KINDS:
        if kind in given:
            if supplied[kind] is None:
                raise ValueError(
                    f"{location}: it describes {kind!r}, but no {kind} catalog "
                    f"was supplied, so that catalog is the packaged default "
                    f"and its provenance is already known; supply the {kind} "
                    f"catalog or drop the entry"
                )
            resolved[kind] = given[kind]
        elif supplied[kind] is None:
            packaged = _BUILTIN_MANIFESTS['default'].get(kind)
            if packaged is not None:
                resolved[kind] = dict(packaged)
    return resolved


class Catalogs:
    '''
    The three catalogs the simulator draws from: facilities, appliances and
    loggers.

    Each argument is a list of dicts; anything left out falls back to the
    packaged default. Records are normalized and validated on the way in, so a
    Catalogs object that exists is one every consumer can read without
    re-checking. The lists are copies -- loading never mutates the dicts handed
    in, nor the packaged literals.

    `manifest` is optional provenance, keyed by catalog kind -- see
    `MANIFEST_FILENAME`. It is read for you from a `manifest.json` by
    `from_dir()`, and carried in code for the packaged catalogs. Whatever the
    route, the resulting `Catalogs.manifest` describes the catalogs this object
    actually holds, so a kind left to fall back reports the packaged origin
    rather than the caller's.
    '''

    def __init__(self, facilities=None, appliances=None, loggers=None,
                 manifest=None):
        self.facilities = _prepare(_as_loaded(facilities, 'facilities'), 'facilities')
        self.appliances = _prepare(_as_loaded(appliances, 'appliances'), 'appliances')
        self.loggers = _prepare(_as_loaded(loggers, 'loggers'), 'loggers')
        self.manifest = _resolve_manifest(manifest, {
            'facilities': facilities,
            'appliances': appliances,
            'loggers': loggers,
        })

    @classmethod
    def builtin(cls, name='default'):
        '''
        Load a named catalog packaged with the simulator.

            Catalogs.builtin('default')         # the illustrative sample
            Catalogs.builtin('nigeria-sokoto')  # 46 real Sokoto facilities
            Catalogs.builtin('pqs-e003-full')   # the whole PQS equipment list

        A builtin only replaces the catalogs it names; the rest stay the
        packaged default. Each carries its provenance in `.manifest`.
        '''
        if name not in BUILTIN_CATALOGS:
            raise ValueError(
                f"Unknown builtin catalog {name!r}: expected one of "
                f"{', '.join(repr(n) for n in BUILTIN_CATALOGS)}"
            )
        return cls(
            manifest=_BUILTIN_MANIFESTS.get(name), **_BUILTIN_RECORDS[name]
        )

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

        A `manifest.json` in the directory is read as the catalogs' provenance
        and exposed as `.manifest`. It is optional and its absence is silent.
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
        manifests = [
            entry for entry in candidates
            if entry.name.lower() == MANIFEST_FILENAME
        ]
        if len(manifests) > 1:
            raise ValueError(
                f"{directory}: found more than one manifest ("
                + ', '.join(entry.name for entry in manifests)
                + "); keep only one"
            )
        manifest = _read_manifest(manifests[0]) if manifests else None
        for kind in manifest or ():
            if kind not in found:
                raise ValueError(
                    f"{manifests[0]}: describes {kind!r}, but the directory "
                    f"has no {kind} catalog file, so that catalog is the "
                    f"packaged default; add the file or drop the entry"
                )
        return cls(manifest=manifest, **found)

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


# ---------------------------------------------------------------------------
# Resolving the catalogs a consumer gets when it was passed none
# ---------------------------------------------------------------------------

#: Cache for `default_catalogs()`. Private, and cleared only through
#: `reset_default_catalogs()`, so that a test which changes the environment can
#: put the module back the way it found it.
_default_catalogs = None


def default_catalogs():
    '''
    The catalogs a consumer falls back to when it was handed none.

    Resolved from `CCESIM_CATALOG_DIR` when that names a directory, and from
    the packaged defaults otherwise. The result is cached, because a load test
    builds many devices and none of them should re-read the files.

    An unusable `CCESIM_CATALOG_DIR` is an error, never a quiet fall back to
    the packaged catalogs: a user who set it meant it, and silently simulating
    the packaged example facilities instead of their own country is the failure
    this whole module exists to prevent. An unset or empty value means "not asked for", which is
    what an exported-but-blank variable in a shell profile means in practice.
    '''
    global _default_catalogs
    if _default_catalogs is None:
        directory = os.environ.get(CATALOG_DIR_ENV, '').strip()
        if directory:
            try:
                _default_catalogs = Catalogs.from_dir(directory)
            except (ValueError, TypeError, OSError) as exc:
                raise ValueError(
                    f"{CATALOG_DIR_ENV}={directory!r}: {exc}"
                ) from None
        else:
            _default_catalogs = Catalogs()
    return _default_catalogs


def reset_default_catalogs():
    '''
    Drop the cached default, so the next `default_catalogs()` re-reads
    `CCESIM_CATALOG_DIR`. Exists for tests: without it the cache would make
    the resolution order depend on which test ran first.
    '''
    global _default_catalogs
    _default_catalogs = None
