from django.core.management.base import BaseCommand
from django.utils import timezone
from members.models import Member
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Create sample notifications for testing'

    def handle(self, *args, **options):
        members = Member.objects.all()[:5]
        
        if not members:
            self.stdout.write(self.style.WARNING('No members found. Create members first.'))
            return

        sample_notifications = [
            {
                'notification_type': 'success',
                'title': 'Loan Application Approved',
                'message': 'Your loan application for KES 50,000 has been approved. Check your dashboard for disbursement details.',
            },
            {
                'notification_type': 'info',
                'title': 'Monthly Contribution Deadline',
                'message': 'Your monthly contribution of KES 5,000 is due by the 25th of this month.',
            },
            {
                'notification_type': 'warning',
                'title': 'Loan Payment Reminder',
                'message': 'Your next loan payment of KES 8,500 is due in 3 days.',
            },
            {
                'notification_type': 'success',
                'title': 'Dividend Payment Processed',
                'message': 'Your dividend of KES 2,500 has been credited to your account.',
            },
            {
                'notification_type': 'alert',
                'title': 'Account Verification Required',
                'message': 'Please verify your email address to continue using the portal.',
            },
        ]

        created_count = 0
        for i, member in enumerate(members):
            for j, notif_data in enumerate(sample_notifications):
                notification = Notification.objects.create(
                    member=member,
                    notification_type=notif_data['notification_type'],
                    title=notif_data['title'],
                    message=notif_data['message'],
                    is_read=j % 2 == 0,  # Alternate between read and unread
                )
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {created_count} sample notifications for {len(members)} members'
            )
        )
