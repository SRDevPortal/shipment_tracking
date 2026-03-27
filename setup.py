import setuptools

with open("requirements.txt") as f:
    install_requires = [line for line in f.read().strip().split("\n") if line]

setuptools.setup(
    name="shipment_tracking",
    version="0.0.1",
    author="Admin",
    author_email="admin@example.com",
    description="Shipment Tracking App",
    packages=setuptools.find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)