from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager para el User custom con email como identificador de login.

    Necesario porque el UserManager por default de Django asume `username`
    como USERNAME_FIELD (ver decisiones_post_auditoria.md #5: pharma_core
    usa username global y eso choca entre tenants).
    """

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('is_staff debe ser True para un superusuario.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('is_superuser debe ser True para un superusuario.')

        return self._create_user(email, password, **extra_fields)
