from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import AdminInvitation

User = get_user_model()


class AdminRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    confirm_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    invitation_token = serializers.CharField(write_only=True, trim_whitespace=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords must match.'})

        token = attrs.get('invitation_token')
        try:
            invitation = AdminInvitation.objects.get(token=token)
        except AdminInvitation.DoesNotExist:
            raise serializers.ValidationError({'invitation_token': 'Invalid invitation token.'})

        if invitation.used:
            raise serializers.ValidationError({'invitation_token': 'This invitation token has already been used.'})

        if invitation.expires_at and timezone.now() > invitation.expires_at:
            raise serializers.ValidationError({'invitation_token': 'This invitation token has expired.'})

        if invitation.email and attrs.get('email').lower() != invitation.email.lower():
            raise serializers.ValidationError({'email': 'Email does not match the invitation.'})

        self.invitation = invitation
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        validated_data.pop('invitation_token')
        password = validated_data.pop('password')
        email = validated_data.pop('email')
        full_name = validated_data.pop('full_name')

        invitation = self.invitation
        user = User.objects.create_user(
            email=email,
            password=password,
            full_name=full_name,
            role=invitation.role,
            is_staff=True,
            is_superuser=True,
        )

        invitation.used = True
        invitation.used_at = timezone.now()
        invitation.save(update_fields=['used', 'used_at'])

        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()

    def validate_identifier(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Provide an email address or member number.')
        return value

    def validate(self, attrs):
        identifier = attrs['identifier']
        try:
            if '@' in identifier:
                user = User.objects.get(email__iexact=identifier)
            else:
                from members.models import Member
                member = Member.objects.get(member_number__iexact=identifier)
                user = member.user
        except Exception:
            raise serializers.ValidationError({'identifier': 'No user found for the supplied identifier.'})

        if not user.is_active:
            raise serializers.ValidationError({'identifier': 'User account is inactive.'})

        attrs['user'] = user
        return attrs


class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        password = attrs.get('new_password')
        confirm = attrs.get('confirm_password')
        if password != confirm:
            raise serializers.ValidationError({'confirm_password': 'Passwords must match.'})

        try:
            uid = force_str(urlsafe_base64_decode(attrs.get('uidb64')))
            user = User.objects.get(pk=uid)
        except Exception:
            raise serializers.ValidationError({'uidb64': 'Invalid reset link.'})

        if not default_token_generator.check_token(user, attrs.get('token')):
            raise serializers.ValidationError({'token': 'Invalid or expired reset token.'})

        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user
