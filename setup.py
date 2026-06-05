from setuptools import find_packages, setup

package_name = "robocon_coop_comm"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="ROBOCON Team",
    maintainer_email="team@example.com",
    description="R1/R2 cooperative optical communication for ROBOCON 2026",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "demo_cli = robocon_coop_comm.demo_cli:main",
            "demo_cv = robocon_coop_comm.demo_cv:main",
            "r1_fsm_node = robocon_coop_comm.ros_nodes.r1_fsm_node:main",
            "r2_fsm_node = robocon_coop_comm.ros_nodes.r2_fsm_node:main",
        ],
    },
)
