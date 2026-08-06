from glob import glob

from setuptools import find_packages, setup


package_name = 'dual_arm_lift_coordinator'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/params', glob('params/*.example.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    description='RM65 网关只读 HEALTH TCP 客户端。',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'rm65_health_client = dual_arm_lift_coordinator.node:main',
        ],
    },
)
