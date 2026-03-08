# -*- coding: utf-8 -*-
# Copyright (c) 2026, Jazira App
# License: MIT

"""
Patch: URY POS Branch Setup
============================
Smart, Saripul, Xalq bank filiallari uchun URY POS to'liq sozlamasi.
"""

from jazira_app.jazira_app.setup.ury_pos_setup import execute


def execute():
    from jazira_app.jazira_app.setup import ury_pos_setup
    ury_pos_setup.execute()
