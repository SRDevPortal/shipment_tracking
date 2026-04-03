from .setup.runner import setup_all


def after_install():
    setup_all()


def after_migrate():
    # DO NOT reload doctypes here
    setup_all(skip_reload=True)