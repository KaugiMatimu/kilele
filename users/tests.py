from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from members.models import Member

User = get_user_model()


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='tester@example.com',
            password='old-password-123',
            full_name='Tester',
        )
        Member.objects.create(user=self.user, member_number='TEST123', status='active')

    def test_password_reset_request_returns_200(self):
        response = self.client.post('/api/users/password-reset/', {'identifier': 'TEST123'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('email_sent'))

    def test_password_reset_confirm_with_valid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.post(
            '/api/users/password-reset-confirm/',
            {
                'uidb64': uid,
                'token': token,
                'new_password': 'new-password-123',
                'confirm_password': 'new-password-123',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('detail'), 'Password has been reset successfully.')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('new-password-123'))

    def test_password_reset_confirm_with_invalid_uid(self):
        response = self.client.post(
            '/api/users/password-reset-confirm/',
            {
                'uidb64': 'invalid',
                'token': 'invalid-token',
                'new_password': 'new-password-123',
                'confirm_password': 'new-password-123',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('uidb64', response.data)
