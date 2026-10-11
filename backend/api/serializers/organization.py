"""Organization serializers."""

from rest_framework import serializers

from ..models import Region, Office, StaffProfile, DormType


# ===========================================
# REGION / OFFICE / STAFF SERIALIZERS
# ===========================================
class RegionSerializer(serializers.ModelSerializer):
    """Serialize region data"""

    class Meta:
        model = Region
        fields = ['id', 'name']

class OfficeSerializer(serializers.ModelSerializer):
    """Serialize office data"""

    office_type_display = serializers.CharField(source='get_office_type_display', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = Office
        fields = [
            'id',
            'name',
            'office_type',
            'office_type_display',
            'region',
            'region_name',
        ]

    def validate(self, attrs):
        office_type = attrs.get('office_type', getattr(self.instance, 'office_type', None))
        region = attrs.get('region', getattr(self.instance, 'region', None))

        if office_type == Office.OfficeType.REGIONAL and not region:
            raise serializers.ValidationError({
                'region': 'Regional office must have a region.'
            })

        if office_type == Office.OfficeType.CENTRAL and region:
            raise serializers.ValidationError({
                'region': 'Central office should not be linked to a region.'
            })

        return attrs


class StaffProfileSerializer(serializers.ModelSerializer):
    """Serialize staff profile data"""

    user_email = serializers.CharField(source='user.email', read_only=True)
    user_full_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    office_name = serializers.CharField(source='office.name', read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            'id',
            'user',
            'user_email',
            'user_full_name',
            'role',
            'role_display',
            'office',
            'office_name',
        ]

    def get_user_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.email


# ===========================================
# DORM / BUILDING SERIALIZERS
# ===========================================
class DormTypeSerializer(serializers.ModelSerializer):
    """Serialize dorm type data"""

    region_name = serializers.CharField(source='region.name', read_only=True)

    class Meta:
        model = DormType
        fields = ['id', 'code', 'name', 'region', 'region_name']
