from django.apps import AppConfig
from django.db.models.signals import post_migrate


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        post_migrate.connect(create_default_admin, sender=self)


def create_default_admin(sender, **kwargs):
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db.utils import OperationalError

    User = get_user_model()
    try:
        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        admin_password = getattr(settings, 'ADMIN_PASSWORD', None)
        if not admin_email or not admin_password:
            return

        admin_user = User.objects.filter(email__iexact=admin_email).first()
        if not admin_user:
            User.objects.create_superuser(
                email=admin_email,
                password=admin_password,
                full_name='Admin User',
            )
            return

        if settings.DEBUG and not admin_user.check_password(admin_password):
            admin_user.set_password(admin_password)
            admin_user.save(update_fields=['password'])
    except OperationalError:
        pass
    except Exception:
        pass
