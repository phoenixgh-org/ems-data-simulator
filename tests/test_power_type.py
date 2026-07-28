"""Tests for how an appliance's power type is resolved.

An explicit `power_type` on an appliance record always wins; the free-text
`type` string is only sniffed as a fallback. Getting this wrong is not
cosmetic — the power type selects the whole physical model (icebank behaviour,
solar bell curve, holdover, alarm profile) — and the old sniff-only path was
silently wrong for any catalog not worded like the packaged E003 export.
"""

import logging

import pytest

from ccesim.device import (
    BaseRtmDevice,
    MonitoringDeviceConfig,
    _infer_power_type,
    _resolve_power_type,
)
from ccesim.devicegroups import Device, DeviceGroup, fridges, validate_power_type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _appliance_dict(**overrides):
    """A minimal appliance catalog record, in packaged-catalog key style."""
    record = {
        "APQS": "E003/999",
        "type": "Refrigerator (photovoltaic)",
        "AMFR": "Acme Cold Chain Ltd",
        "AMOD": "PV-100",
    }
    record.update(overrides)
    return record


def _device(**overrides):
    return Device.from_dict(_appliance_dict(**overrides))


def _device_with_appliance(appliance):
    """Build an EMS BaseRtmDevice whose appliance is the one supplied."""
    config = MonitoringDeviceConfig(
        type='ems',
        upload_interval=3600,
        sample_interval=900,
    )
    config.appliance = appliance
    config.device = appliance
    return BaseRtmDevice(config)


# ===========================================================================
# Explicit power_type wins
# ===========================================================================

class TestExplicitPowerTypeWins:
    """An explicit power_type overrides whatever the type string suggests."""

    def test_solar_declared_on_a_type_string_with_no_solar_keyword(self):
        # 'Refrigerator (photovoltaic)' sniffs as mains, which is wrong.
        appliance = _device(power_type='solar')
        assert _infer_power_type(appliance.type) == 'mains'
        assert _resolve_power_type(appliance) == 'solar'

    def test_declared_solar_selects_the_solar_power_model(self):
        device = _device_with_appliance(_device(power_type='solar'))
        assert device.powersource == 'solar'
        assert device.sim_config.power.power_type == 'solar'

    def test_mains_declared_on_a_solar_type_string(self):
        appliance = _device(type='Solar direct drive refrigerator', power_type='mains')
        assert _infer_power_type(appliance.type) == 'solar'
        assert _resolve_power_type(appliance) == 'mains'

    def test_declared_mains_selects_the_mains_power_model(self):
        appliance = _device(type='Solar direct drive refrigerator', power_type='mains')
        device = _device_with_appliance(appliance)
        assert device.powersource == 'mains'
        assert device.sim_config.power.power_type == 'mains'

    def test_explicit_value_is_case_and_whitespace_insensitive(self):
        assert _device(power_type=' Solar ').power_type == 'solar'
        assert _device(power_type='MAINS').power_type == 'mains'


# ===========================================================================
# Fallback to the type-string sniff
# ===========================================================================

class TestSniffFallback:
    """Without an explicit value the existing string sniff is unchanged."""

    def test_absent_power_type_still_sniffs_solar(self):
        appliance = _device(type='Solar direct drive refrigerator')
        assert appliance.power_type is None
        assert _resolve_power_type(appliance) == 'solar'

    def test_absent_power_type_still_sniffs_sdd(self):
        assert _resolve_power_type(_device(type='SDD fridge')) == 'solar'

    def test_absent_power_type_still_sniffs_mains(self):
        assert _resolve_power_type(_device(type='Icelined refrigerator')) == 'mains'

    def test_absent_power_type_keeps_the_silent_photovoltaic_miss(self):
        # Documents the fallback's known blind spot: the sniff cannot know this
        # is solar, which is exactly why power_type exists.
        assert _resolve_power_type(_device()) == 'mains'

    def test_sniff_is_logged_at_info(self, caplog):
        appliance = _device(type='Icelined refrigerator')
        with caplog.at_level(logging.INFO, logger='ccesim.device'):
            _resolve_power_type(appliance)
        assert any(
            'E003/999' in r.getMessage() and 'declares no power_type' in r.getMessage()
            for r in caplog.records
        )

    def test_explicit_value_is_not_logged_as_a_sniff(self, caplog):
        with caplog.at_level(logging.INFO, logger='ccesim.device'):
            _resolve_power_type(_device(power_type='solar'))
        assert not any('declares no power_type' in r.getMessage() for r in caplog.records)


# ===========================================================================
# Validation of explicit values
# ===========================================================================

class TestInvalidPowerType:
    """A bad explicit value fails loudly instead of defaulting to mains."""

    def test_from_dict_rejects_unknown_value(self):
        with pytest.raises(ValueError) as excinfo:
            _device(power_type='photovoltaic')
        assert 'photovoltaic' in str(excinfo.value)

    def test_error_names_the_offending_appliance(self):
        with pytest.raises(ValueError) as excinfo:
            _device(power_type='wind')
        message = str(excinfo.value)
        assert 'E003/999' in message
        assert 'Acme Cold Chain Ltd' in message
        assert 'PV-100' in message

    def test_non_string_value_is_rejected(self):
        with pytest.raises(ValueError):
            _device(power_type=True)

    def test_devicegroup_rejects_a_bad_row_at_load(self):
        catalog = [_appliance_dict(), _appliance_dict(APQS='E003/998', power_type='diesel')]
        with pytest.raises(ValueError) as excinfo:
            DeviceGroup(catalog)
        assert 'E003/998' in str(excinfo.value)

    def test_resolve_rejects_a_device_built_without_from_dict(self):
        # Device(...) constructed directly bypasses from_dict's validation, so
        # the resolver has to catch it rather than fall through to mains.
        appliance = Device(
            manufacturer='Acme Cold Chain Ltd',
            model='PV-100',
            pqs_code='E003/999',
            type='Icelined refrigerator',
            power_type='diesel',
        )
        with pytest.raises(ValueError):
            _resolve_power_type(appliance)

    def test_validate_power_type_passes_none_through(self):
        assert validate_power_type(None, 'E003/999') is None


# ===========================================================================
# The packaged catalog
# ===========================================================================

class TestPackagedCatalog:
    """The shipped appliances declare their power type; none rely on the sniff."""

    def test_every_fridge_declares_a_valid_power_type(self):
        for record in fridges:
            assert record['power_type'] in ('solar', 'mains'), record['APQS']

    def test_declared_values_agree_with_the_type_string_sniff(self):
        # One deliberate exception: E003/124 (B Medical TCW120SDD) is a solar
        # direct drive whose type string says only 'Vaccine Refrigerator /
        # Ice-pack Freezer', so the sniff had it wrong.
        disagreements = {
            record['APQS']
            for record in fridges
            if record['power_type'] != _infer_power_type(record['type'])
        }
        assert disagreements == {'E003/124'}

    def test_packaged_appliances_never_take_the_sniff_path(self, caplog):
        group = DeviceGroup(fridges)
        with caplog.at_level(logging.INFO, logger='ccesim.device'):
            for record in fridges:
                _resolve_power_type(Device.from_dict(record))
        assert group.list() is fridges
        assert not any('declares no power_type' in r.getMessage() for r in caplog.records)
