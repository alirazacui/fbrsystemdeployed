"""
users/serializers.py
"""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User, UserStatus


# ---------------------------------------------------------------------------
# JWT — custom claims
# ---------------------------------------------------------------------------

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Adds role, company_id, and status into the JWT payload so that
    DRF permission classes can read them from the token without an
    extra database hit on every request.

    Payload example:
        {
            "user_id": 42,
            "email": "owner@abcstore.com",
            "role": "owner",
            "company_id": 7,
            "status": "active"
        }
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"]      = user.email
        token["role"]       = user.role
        token["company_id"] = user.company_id   # None for platform users
        token["status"]     = user.status
        return token

    def validate(self, attrs):
        """
        Block login for inactive or suspended users BEFORE issuing a token.
        Django's default only checks is_active; we also check our status field.
        """
        data = super().validate(attrs)

        user = self.user
        if user.status == UserStatus.INACTIVE:
            raise serializers.ValidationError(
                "This account has been deactivated. Contact your administrator."
            )
        if user.status == UserStatus.SUSPENDED:
            raise serializers.ValidationError(
                "This account has been suspended. Contact the platform administrator."
            )

        # Add user info to the login response alongside the tokens
        data["user"] = {
            "id":         user.id,
            "email":      user.email,
            "full_name":  user.get_full_name(),
            "role":       user.role,
            "company_id": user.company_id,
            "status":     user.status,
        }
        return data


# ---------------------------------------------------------------------------
# User serializers
# ---------------------------------------------------------------------------

class UserListSerializer(serializers.ModelSerializer):
    """
    Lightweight — for lists and dropdowns.
    """
    full_name    = serializers.CharField(source="get_full_name", read_only=True)
    company_name = serializers.CharField(
        source="company.business_name", read_only=True, default=None
    )

    class Meta:
        model  = User
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "status",
            "company_id",
            "company_name",
            "date_joined",
        ]
        read_only_fields = fields


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Full detail — for retrieve and update (no password here).
    """
    full_name    = serializers.CharField(source="get_full_name", read_only=True)
    company_name = serializers.CharField(
        source="company.business_name", read_only=True, default=None
    )
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model  = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "status",
            "company",
            "company_name",
            "created_by",
            "created_by_email",
            "date_joined",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "full_name",
            "company_name",
            "created_by",
            "created_by_email",
            "date_joined",
            "updated_at",
        ]


class CreateAdminStaffSerializer(serializers.ModelSerializer):
    """
    Admin creates Admin Staff.
    No company field — platform users never belong to a company.
    Password is set manually by the creator.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    class Meta:
        model  = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "password",
            "confirm_password",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        request = self.context.get("request")
        user = User.objects.create_user(
            email      = validated_data["email"],
            password   = validated_data["password"],
            first_name = validated_data.get("first_name", ""),
            last_name  = validated_data.get("last_name", ""),
            phone      = validated_data.get("phone", ""),
            role       = User.Role.ADMIN_STAFF,
            status     = UserStatus.ACTIVE,
            created_by = request.user if request else None,
        )
        return user


class CreateOwnerSerializer(serializers.ModelSerializer):
    """
    Admin creates an Owner for a specific Company.
    Once saved, the signal auto-grants all company-module permissions.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    class Meta:
        model  = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "company",
            "password",
            "confirm_password",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def validate_company(self, company):
        """
        Reject if the company already has an owner
        OR if the company is inactive.
        """
        from users.models import User as UserModel
        if not company.is_active:
            raise serializers.ValidationError(
                f"Company '{company.business_name}' is inactive. Activate it first."
            )
        if UserModel.objects.filter(company=company, role=User.Role.OWNER).exists():
            raise serializers.ValidationError(
                f"Company '{company.business_name}' already has an owner."
            )
        return company

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        request = self.context.get("request")
        user = User.objects.create_user(
            email      = validated_data["email"],
            password   = validated_data["password"],
            first_name = validated_data.get("first_name", ""),
            last_name  = validated_data.get("last_name", ""),
            phone      = validated_data.get("phone", ""),
            role       = User.Role.OWNER,
            company    = validated_data["company"],
            status     = UserStatus.ACTIVE,
            created_by = request.user if request else None,
        )
        # Signal auto_grant_owner_permissions fires here automatically
        return user


class CreateClientUserSerializer(serializers.ModelSerializer):
    """
    Owner creates Manager / Cashier / Salesperson inside their own company.
    The company is taken from the requesting owner — never from the request body.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    role = serializers.ChoiceField(
        choices=[
            User.Role.MANAGER,
            User.Role.CASHIER,
            User.Role.SALESPERSON,
        ]
    )

    class Meta:
        model  = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "password",
            "confirm_password",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        request = self.context.get("request")
        # Company comes from the requesting owner — not from the payload
        user = User.objects.create_user(
            email      = validated_data["email"],
            password   = validated_data["password"],
            first_name = validated_data.get("first_name", ""),
            last_name  = validated_data.get("last_name", ""),
            phone      = validated_data.get("phone", ""),
            role       = validated_data["role"],
            company    = request.user.company,
            status     = UserStatus.ACTIVE,
            created_by = request.user,
        )
        return user


class UpdateUserStatusSerializer(serializers.ModelSerializer):
    """
    Dedicated serializer just for changing a user's status.
    Keeps status changes as an explicit separate action.
    """

    class Meta:
        model  = User
        fields = ["status"]

    def validate_status(self, value):
        request = self.context.get("request")
        target  = self.instance

        # Only platform Admin can suspend or un-suspend
        if value == UserStatus.SUSPENDED:
            if not request.user.is_platform_admin:
                raise serializers.ValidationError(
                    "Only platform Admin can suspend a user."
                )

        # Owner cannot reactivate a suspended user
        if (
            target.status == UserStatus.SUSPENDED
            and value == UserStatus.ACTIVE
            and not request.user.is_platform_admin
        ):
            raise serializers.ValidationError(
                "Only platform Admin can lift a suspension."
            )

        return value


class ChangePasswordSerializer(serializers.Serializer):
    """
    Allows a user to change their own password.
    """
    old_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    confirm_new_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_new_password"]:
            raise serializers.ValidationError(
                {"confirm_new_password": "New passwords do not match."}
            )
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user