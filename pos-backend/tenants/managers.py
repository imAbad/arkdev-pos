from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager para el User custom — email ya NO es obligatorio (una
    cuenta puede darse de alta solo con `username`, ver tenants.models.User)
    a diferencia del UserManager por default de Django, que sí lo asume.
    """

    use_in_migrations = True

    def _create_user(self, email=None, password=None, **extra_fields):
        username = extra_fields.get('username')
        if not email and not username:
            raise ValueError('Debe indicarse email o username.')
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        # El superusuario SÍ sigue requiriendo email explícito — cuenta
        # operativa creada por Carlos/ops, no una cuenta de mostrador.
        if not email:
            raise ValueError('El superusuario requiere email.')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('is_staff debe ser True para un superusuario.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('is_superuser debe ser True para un superusuario.')

        return self._create_user(email, password, **extra_fields)
