from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.conf import settings
from django.core.mail import send_mail

from .serializers import AdminRegistrationSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer


class AdminRegistrationView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = AdminRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                'id': user.id,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
            },
            status=status.HTTP_201_CREATED,
        )


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        reset_url = f"{settings.FRONTEND_URL}/reset-password?uidb64={uid}&token={token}"

        # Send the password reset email.
        subject = 'Reset your Kilele Ridge password'
        message = (
            f'Hello {user.full_name},\n\n'
            f'Use the link below to reset your password:\n\n{reset_url}\n\n'
            'If you did not request a reset, please ignore this email.\n\n'
            'Thanks,\nKilele Ridge'
        )
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient_list = [user.email]
        try:
            send_mail(subject, message, from_email, recipient_list, fail_silently=False)
            sent = True
        except Exception as exc:
            sent = False
            sent_error = str(exc)

        response_data = {
            'detail': 'Password reset request processed.',
            'reset_url': reset_url,
        }
        if sent:
            response_data['email_sent'] = True
        else:
            response_data['email_sent'] = False
            response_data['email_error'] = sent_error
            response_data['note'] = 'Email failed to send. Use the reset_url directly in dev.'

        return Response(response_data, status=status.HTTP_200_OK)


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({'detail': 'Password has been reset successfully.'}, status=status.HTTP_200_OK)
