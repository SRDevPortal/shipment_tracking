from .setup.runner import setup_all


def after_install():
    setup_all()


def after_migrate():
    setup_all()
