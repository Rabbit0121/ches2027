"""Shared path validation and budgets for electrical searches."""
from pathlib import Path
from .bidirectional import Config


def configured_path(value):
    if 'the/path/of/' in str(value):
        raise ValueError('Replace the/path/of/xxx with a configured location')
    return Path(value)


def search_config(settings, timing, seconds=None):
    return Config(seconds=seconds or settings['search_seconds'], timing=timing,
                  max_states=settings['max_states'], max_demands=settings['max_demands'],
                  slew_ps=settings['slew_ps'], output_load_ff=settings['load_ff'])
