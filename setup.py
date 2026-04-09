from setuptools import setup, find_packages

setup(
    name="shipment_tracking",
    version="0.0.1",
    description="Shipkia shipment sync and tracking for ERPNext",
    author="SRIAAS",
    author_email="webdevelopersriaas@gmail.com",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)