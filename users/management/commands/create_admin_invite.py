import secrets
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import AdminInvitation


class Command(BaseCommand):
    help = 'Create a secure admin invitation token.'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Optional invited admin email')
        parser.add_argument('--full-name', type=str, help='Optional invited admin full name')
        parser.add_argument('--role', type=str, default='admin', help='Role for the invited user')
        parser.add_argument('--expires-in', type=int, default=7, help='Expiration in days')

    def handle(self, *args, **options):
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(days=options['expires_in'])

        invitation = AdminInvitation.objects.create(
            token=token,
            email=options.get('email') or '',
            full_name=options.get('full_name') or '',
            role=options['role'],
            expires_at=expires_at,
        )

        self.stdout.write(self.style.SUCCESS('Admin invitation created successfully.'))
        self.stdout.write(f'Token: {invitation.token}')
        self.stdout.write(f'Link: http://localhost:3000/admin-register?token={invitation.token}')
