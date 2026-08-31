"""
Tracks human-in-the-loop decisions on flags: pending / confirmed / dismissed.
Deliberately simple (JSON file) since this is a hackathon prototype -
swap for a real DB table (flag_id, status, updated_at, updated_by) in production.
"""
import json
import os

import config


def _load():
    if not os.path.exists(config.FLAG_STATUS_FILE):
        return {}
    with open(config.FLAG_STATUS_FILE, 'r') as f:
        return json.load(f)


def _save(data):
    with open(config.FLAG_STATUS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_status(flag_id):
    return _load().get(flag_id, "pending")


def set_status(flag_id, status):
    if status not in ("pending", "confirmed", "dismissed"):
        raise ValueError(f"Invalid status: {status}")
    data = _load()
    data[flag_id] = status
    _save(data)


def apply_statuses(flags):
    """Attach current status to each flag dict, in place. Returns the list."""
    statuses = _load()
    for flag in flags:
        flag['status'] = statuses.get(flag.get('id'), 'pending')
    return flags
