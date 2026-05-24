"""Shared helpers for domain API routers."""

import logging

from scripts.server import dependencies as deps

logger = logging.getLogger(__name__)

verify_api_key = deps.verify_api_key


def get_db_manager():
    return deps.get_db()


def get_data_manager():
    return deps.get_db()


def clean_record(record):
    return deps.clean_record(record)


def clean_records(records):
    return deps.clean_records(records)
