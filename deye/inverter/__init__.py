"""Робота з інвертором: регістри і з'єднання з логером."""
from deye.inverter.link import LINK_ERRORS, Link, describe_error, solarman_connector
from deye.inverter.registers import ModbusClient, dump_registers, read_reading

__all__ = ["LINK_ERRORS", "Link", "ModbusClient", "describe_error", "dump_registers", "read_reading",
           "solarman_connector"]
