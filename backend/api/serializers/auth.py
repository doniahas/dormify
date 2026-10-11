"""Authentication serializers."""

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers


User = get_user_model()


# ===========================================
# USER SERIALIZERS
# ===========================================
class UserSerializer(serializers.ModelSerializer):
    """Serialize user data (without password)"""

    role_display = serializers.CharField(source='get_role_display', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    full_name = serializers.SerializerMethodField()
    is_central_admin = serializers.BooleanField(read_only=True)
    is_boss = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'role',
            'role_display',
            'region',
            'region_name',
            'phone',
            'is_active',
            'date_joined',
            'is_central_admin',
            'is_boss',
        ]
        read_only_fields = [
            'id',
            'date_joined',
            'full_name',
            'is_central_admin',
            'is_boss',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.email


class LoginSerializer(serializers.Serializer):
    """Serialize login request"""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError('אימייל או סיסמה שגויים')
            if not user.is_active:
                raise serializers.ValidationError('המשתמש אינו פעיל')
            data['user'] = user
        else:
            raise serializers.ValidationError('נדרש אימייל וסיסמה')

        return data


# G3-01: RegisterSerializer (backed the now-removed public /auth/register/
# endpoint) intentionally deleted - the only authorized staff-creation path
# is accounts.serializers.StaffUserSerializer via /api/staff-users/.
