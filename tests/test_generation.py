import pytest
import datetime as dt
import random
import statistics
from ccesim.device import MonitoringDeviceConfig, BaseRtmDevice
from ccesim.facilities import Facility
from ccesim.schemas import RtmdReport, EmsReport


@pytest.fixture
def report_time():
    return dt.datetime(2024, 6, 15, 12, 0, 0)


@pytest.fixture
def rtmd_device():
    config = MonitoringDeviceConfig(
        type='rtmd',
        upload_interval=3600,
        sample_interval=900,
    )
    return BaseRtmDevice(config)


@pytest.fixture
def ems_device():
    config = MonitoringDeviceConfig(
        type='ems',
        upload_interval=3600,
        sample_interval=900,
    )
    return BaseRtmDevice(config)


def test_rtmd_initialization(rtmd_device):
    """Test if RTMD device initializes correctly."""
    assert rtmd_device.config.type == 'rtmd'
    assert rtmd_device.config.upload_interval == 3600
    assert rtmd_device.config.sample_interval == 900
    assert rtmd_device.simulator_state is None
    assert rtmd_device.cid is not None
    assert rtmd_device.lmfr != rtmd_device.amfr or rtmd_device.lmod != rtmd_device.amod


def test_ems_initialization(ems_device):
    """Test if EMS device initializes correctly."""
    assert ems_device.config.type == 'ems'
    assert ems_device.lmfr == ems_device.amfr
    assert ems_device.lmod == ems_device.amod


def test_create_rtmd_report(rtmd_device, report_time):
    """Test if an RTMD report is generated correctly."""
    report = rtmd_device.create_report(report_time=report_time)
    assert isinstance(report, RtmdReport)
    assert report.CID == rtmd_device.cid
    assert len(report.records) == 4  # 3600/900 = 4 records


def test_create_ems_report(ems_device, report_time):
    """Test if an EMS report is generated correctly."""
    report = ems_device.create_report(report_time=report_time)
    assert isinstance(report, EmsReport)
    assert report.CID == ems_device.cid
    assert len(report.records) == 4


def test_multiple_reports(rtmd_device, report_time):
    """Test multiple sequential reports with state continuity."""
    reports = []
    t = report_time
    for _ in range(5):
        report = rtmd_device.create_report(report_time=t)
        reports.append(report)
        t += dt.timedelta(seconds=3600)

    for r in reports:
        assert isinstance(r, RtmdReport)
        assert len(r.records) == 4

    # State should be initialized after first report
    assert rtmd_device.simulator_state is not None


def test_report_timestamps(ems_device, report_time):
    """Test that record timestamps are correctly spaced."""
    report = ems_device.create_report(report_time=report_time)
    timestamps = [r.ABST for r in report.records]

    for i in range(1, len(timestamps)):
        delta = (timestamps[i] - timestamps[i - 1]).total_seconds()
        assert delta == 900


def test_tvc_in_range(ems_device, report_time):
    """Test that TVC stays in a reasonable range for normal operation."""
    reports = []
    t = report_time
    for _ in range(10):
        report = ems_device.create_report(report_time=t)
        reports.append(report)
        t += dt.timedelta(seconds=3600)

    all_tvcs = [r.TVC for rep in reports for r in rep.records]
    # Under normal operation TVC should stay roughly between -5 and 15
    assert all(tvc > -10 for tvc in all_tvcs), f"TVC too low: {min(all_tvcs)}"
    assert all(tvc < 20 for tvc in all_tvcs), f"TVC too high: {max(all_tvcs)}"


# ---------------------------------------------------------------------------
# Reported coordinates
#
# Facility.get_nudged_coordinates() adds a gauss(0.00001, 0.001) degree offset
# per axis, drawn afresh for every report. The tests below pin the global RNG
# so the values are fixed rather than merely probable, and then assert only
# loose, order-of-magnitude bounds on top -- a change of draw order cannot make
# them flake. The JS port mirrors this; see js/src/device.test.js.
# ---------------------------------------------------------------------------

JITTER_SIGMA = 0.001  # degrees, ~111 m


@pytest.fixture
def seeded_random():
    """Pin the global RNG for the duration of a test, then restore it."""
    state = random.getstate()
    random.seed(20260729)
    yield
    random.setstate(state)


@pytest.fixture
def sited_facility():
    return Facility({
        'facility_name': 'Test Facility',
        'iso': 'KEN',
        'latitude': -1.3,
        'longitude': 36.8,
    })


def _device(type, facility):
    config = MonitoringDeviceConfig(
        type=type,
        upload_interval=3600,
        sample_interval=900,
        facility=facility,
    )
    return BaseRtmDevice(config)


def _sequential_reports(device, report_time, n):
    reports = []
    t = report_time
    for _ in range(n):
        reports.append(device.create_report(report_time=t))
        t += dt.timedelta(seconds=3600)
    return reports


@pytest.mark.parametrize('type', ['rtmd', 'ems'])
def test_reported_coordinates_are_jittered(type, sited_facility, report_time, seeded_random):
    """LAT/LNG are offset from the facility's stored coordinates."""
    report = _device(type, sited_facility).create_report(report_time=report_time)

    assert report.LAT != sited_facility.latitude
    assert report.LNG != sited_facility.longitude
    # Offset is of the right order: a fraction of a degree, not a degree.
    assert abs(report.LAT - sited_facility.latitude) < 12 * JITTER_SIGMA
    assert abs(report.LNG - sited_facility.longitude) < 12 * JITTER_SIGMA


def test_coordinate_jitter_is_drawn_per_report(sited_facility, report_time, seeded_random):
    """Successive reports from one device carry different coordinates."""
    a, b = _sequential_reports(_device('rtmd', sited_facility), report_time, 2)

    assert a.LAT != b.LAT
    assert a.LNG != b.LNG


def test_coordinate_jitter_does_not_mutate_the_facility(sited_facility, report_time, seeded_random):
    """The jitter is report-only: Facility.latitude/longitude stay raw."""
    device = _device('rtmd', sited_facility)
    _sequential_reports(device, report_time, 5)

    assert sited_facility.latitude == -1.3
    assert sited_facility.longitude == 36.8
    assert device.config.facility.latitude == -1.3
    assert device.config.facility.longitude == 36.8


def test_coordinate_jitter_scale(sited_facility, report_time, seeded_random):
    """Every report draws its own offset, all of order sigma."""
    n = 200
    reports = _sequential_reports(_device('rtmd', sited_facility), report_time, n)
    offsets = [r.LAT - sited_facility.latitude for r in reports]

    assert len(set(offsets)) == n
    assert all(abs(d) < 12 * JITTER_SIGMA for d in offsets)
    assert all(d != 0 for d in offsets)

    # Spread is of order sigma, not 0 and not a degree. Wide bounds: with the
    # RNG pinned this is a fixed number, and 200 samples put it well inside.
    sd = statistics.stdev(offsets)
    assert JITTER_SIGMA / 3 < sd < JITTER_SIGMA * 3
