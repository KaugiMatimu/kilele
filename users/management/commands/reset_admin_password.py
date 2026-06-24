from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
import secrets
import string


class Command(BaseCommand):
    help = "Reset the admin user's password and email the new password to the given address."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=getattr(settings, "ADMIN_EMAIL", None),
            help="Email address of the admin user to reset (defaults to settings.ADMIN_EMAIL)",
        )
        parser.add_argument(
            "--length",
            type=int,
            default=14,
            help="Length of the generated password",
        )
        parser.add_argument(
            "--print",
            dest="print_pwd",
            action="store_true",
            help="Print the new password to stdout (for local/dev use)",
        )

    def handle(self, *args, **options):
        email = options.get("email")
        if not email:
            self.stderr.write(self.style.ERROR("No email provided and settings.ADMIN_EMAIL is not set."))
            return

        User = get_user_model()
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"No user found with email {email}"))
            return

        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        new_password = "".join(secrets.choice(alphabet) for _ in range(options.get("length", 14)))
        user.set_password(new_password)
        user.save()

        subject = "Admin password reset"
        message = (
            "Your admin password has been reset.\n\n"
            "New password: %s\n\n"
            "Please change this password immediately after logging in.\n"
            "If you did not request this change, contact the site owner." % new_password
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "webmaster@localhost")

        try:
            send_mail(subject, message, from_email, [email], fail_silently=False)
            self.stdout.write(self.style.SUCCESS(f"Password reset and email sent to {email}"))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to send email: {exc}"))
            self.stderr.write(self.style.WARNING("Password was updated in the database but the email could not be sent."))

        if options.get("print_pwd"):
            self.stdout.write(self.style.WARNING(f"New password for {email}: {new_password}"))
