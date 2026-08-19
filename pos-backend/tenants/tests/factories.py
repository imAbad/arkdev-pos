from tenants.models import Branch, Company, CompanySettings, User, UserProfile


def create_company(name='Tenant', tax_id=None):
    return Company.objects.create(name=name, tax_id=tax_id)


def create_branch(company, name='Sucursal Centro', address=''):
    return Branch.objects.create(company=company, name=name, address=address)


def create_company_settings(company, enabled_modules=None):
    return CompanySettings.objects.create(
        company=company,
        enabled_modules=enabled_modules or {},
    )


def create_user_with_profile(
    email,
    branch,
    role=UserProfile.Role.CAJERO,
    capabilities=None,
    password='testpass123',
    username=None,
    date_of_birth=None,
):
    user = User.objects.create_user(email=email, password=password, username=username)
    profile = UserProfile.objects.create(
        user=user,
        branch=branch,
        role=role,
        capabilities=capabilities or {},
        date_of_birth=date_of_birth,
    )
    return user, profile


def create_full_tenant(
    company_name,
    branch_name,
    user_email,
    role=UserProfile.Role.CAJERO,
    capabilities=None,
):
    """Arma un tenant completo (company + branch + settings + usuario con
    profile) para no repetir el setup en cada test de aislamiento."""
    company = create_company(name=company_name)
    branch = create_branch(company, name=branch_name)
    settings_ = create_company_settings(company)
    user, profile = create_user_with_profile(user_email, branch, role=role, capabilities=capabilities)
    return {
        'company': company,
        'branch': branch,
        'settings': settings_,
        'user': user,
        'profile': profile,
    }
