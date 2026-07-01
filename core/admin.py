from django.contrib.admin import AdminSite
from django.urls import path
from django.template.response import TemplateResponse


class CustomAdminSite(AdminSite):
    site_header = 'Kilele Ridge Admin Portal'
    site_title = 'Kilele Ridge Admin'
    index_title = 'Welcome to Admin Dashboard'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('', self.admin_view(self.dashboard_view), name='index'),
        ]
        return custom_urls + urls[1:]

    def has_permission(self, request):
        return bool(
            request.user.is_active
            and request.user.is_staff
            and getattr(request.user, 'role', None) in ('admin', 'branch_manager', 'accountant')
        )

    def dashboard_view(self, request):
        context = dict(
            self.each_context(request),
            title='Admin Dashboard',
            section_menu=self.get_role_menu(request.user),
            metrics=self.get_dashboard_metrics(),
        )
        return TemplateResponse(request, 'admin/dashboard.html', context)

    def get_role_menu(self, user):
        role = getattr(user, 'role', None)
        base_menu = [
            {'title': 'Members', 'url': '/admin/members/member/'},
            {'title': 'Branches', 'url': '/admin/members/branch/'},
            {'title': 'Workflow Requests', 'url': '/admin/members/workflowrequest/'},
        ]

        if role == 'admin':
            base_menu += [
                {'title': 'User Roles', 'url': '/admin/users/user/'},
                {'title': 'Contribution Plans', 'url': '/admin/contributions/contributionplan/'},
                {'title': 'Loan Products', 'url': '/admin/loans/loanproduct/'},
                {'title': 'Notification Templates', 'url': '/admin/notifications/notificationtemplate/'},
                {'title': 'Business Rules', 'url': '/admin/contributions/businessrule/'},
                {'title': 'Website Content', 'url': '/admin/notifications/websitecontent/'},
                {'title': 'Audit Logs', 'url': '/admin/contributions/auditlog/'},
            ]
        elif role == 'branch_manager':
            base_menu += [
                {'title': 'Loan Applications', 'url': '/admin/loans/loanapplication/'},
                {'title': 'Transactions', 'url': '/admin/contributions/transactionrecord/'},
            ]
        elif role == 'accountant':
            base_menu += [
                {'title': 'Dividends', 'url': '/admin/contributions/dividendrule/'},
                {'title': 'Contributions', 'url': '/admin/contributions/contributionplan/'},
                {'title': 'Audit Logs', 'url': '/admin/contributions/auditlog/'},
            ]

        return base_menu

    def get_dashboard_metrics(self):
        return [
            {'label': 'Total Members', 'value': self.get_model_count('members', 'Member')},
            {'label': 'Pending Requests', 'value': self.get_model_count('members', 'WorkflowRequest', filter_kwargs={'status': 'pending'})},
            {'label': 'Active Loan Products', 'value': self.get_model_count('loans', 'LoanProduct', filter_kwargs={'active': True})},
            {'label': 'Active Contribution Plans', 'value': self.get_model_count('contributions', 'ContributionPlan', filter_kwargs={'active': True})},
        ]

    def get_model_count(self, app_label, model_name, filter_kwargs=None):
        from django.apps import apps
        try:
            model = apps.get_model(app_label, model_name)
            qs = model.objects.all()
            if filter_kwargs:
                qs = qs.filter(**filter_kwargs)
            return qs.count()
        except (LookupError, Exception):
            return 0


custom_admin_site = CustomAdminSite(name='custom_admin')
