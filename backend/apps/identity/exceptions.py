from rest_framework import status
from rest_framework.exceptions import APIException


class AuthenticationError(APIException):
    """Base class for authentication-related errors"""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Authentication failed."
    default_code = "authentication_failed"


class InvalidCredentialsError(AuthenticationError):
    """Raised when username or password is incorrect"""

    default_detail = "Invalid username or password."
    default_code = "invalid_credentials"


class UserNotFoundError(AuthenticationError):
    """Raised when user doesn't exist"""

    default_detail = "Invalid username or password."
    default_code = "user_not_found"


class AccountInactiveError(AuthenticationError):
    """Raised when user account is inactive"""

    default_detail = "This account is inactive. Please contact support."
    default_code = "account_inactive"


class AccountPendingError(AuthenticationError):
    """Raised when user account is pending approval"""

    default_detail = "Your account is pending approval. Please wait for admin approval."
    default_code = "account_pending"


class AccountDeclinedError(AuthenticationError):
    """Raised when user account has been declined"""

    default_detail = "Your account has been declined. Please contact support."
    default_code = "account_declined"


class ValidationError(APIException):
    """Base class for validation errors"""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Validation failed."
    default_code = "validation_error"


class MissingCredentialsError(ValidationError):
    """Raised when username or password is missing"""

    default_detail = "Username and password are required."
    default_code = "missing_credentials"


class PasswordMismatchError(ValidationError):
    """Raised when passwords don't match"""

    default_detail = "Passwords do not match."
    default_code = "password_mismatch"


class InvalidPasswordError(ValidationError):
    """Raised when old password is incorrect"""

    default_detail = "Old password is incorrect."
    default_code = "invalid_password"


class PasswordValidationError(ValidationError):
    """Raised when new password doesn't meet requirements"""

    default_detail = "Password does not meet requirements."
    default_code = "password_validation_error"


class EmailAlreadyExistsError(ValidationError):
    """Raised when email is already in use"""

    default_detail = "This email is already in use."
    default_code = "email_already_exists"


class ResourceNotFoundError(APIException):
    """Base class for resource not found errors"""

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Resource not found."
    default_code = "resource_not_found"


class ChangeRequestNotFoundError(ResourceNotFoundError):
    """Raised when change request is not found"""

    default_detail = "Request not found."
    default_code = "change_request_not_found"


class InvalidTokenError(APIException):
    """Raised when refresh token is invalid"""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The provided refresh token is invalid or already blacklisted."
    default_code = "invalid_token"


class PermissionDeniedError(APIException):
    """Raised when user doesn't have required permissions"""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to perform this action."
    default_code = "permission_denied"
