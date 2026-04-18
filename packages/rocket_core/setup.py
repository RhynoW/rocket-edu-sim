"""
setup.py for rocket-core.

The project directory (packages/rocket_core/) is itself the rocket_core
package, so we map package names to their directories explicitly instead
of relying on find_packages() auto-discovery.
"""
from setuptools import setup

setup(
    package_dir={
        "rocket_core":             ".",
        "rocket_core.constraints": "constraints",
        "rocket_core.mass_budget": "mass_budget",
        "rocket_core.payload":     "payload",
        "rocket_core.propulsion":  "propulsion",
        "rocket_core.staging":     "staging",
        "rocket_core.trajectory":  "trajectory",
        "rocket_core.vehicle":     "vehicle",
    },
    packages=[
        "rocket_core",
        "rocket_core.constraints",
        "rocket_core.mass_budget",
        "rocket_core.payload",
        "rocket_core.propulsion",
        "rocket_core.staging",
        "rocket_core.trajectory",
        "rocket_core.vehicle",
    ],
)
