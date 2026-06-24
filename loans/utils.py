"""Utility functions for loan calculations and penalty accrual"""
from datetime import date, timedelta
from decimal import Decimal


def calculate_monthly_payment(principal, annual_rate, num_months):
    """
    Calculate monthly payment using the amortization formula.
    
    Formula: M = P * [r(1+r)^n] / [(1+r)^n - 1]
    where:
      P = principal
      r = monthly interest rate (annual_rate / 100 / 12)
      n = number of payments
    """
    if num_months <= 0:
        return Decimal('0')
    
    monthly_rate = Decimal(str(annual_rate)) / Decimal('100') / Decimal('12')
    
    if monthly_rate == 0:
        return Decimal(str(principal)) / Decimal(str(num_months))
    
    principal_dec = Decimal(str(principal))
    numerator = monthly_rate * (1 + monthly_rate) ** num_months
    denominator = (1 + monthly_rate) ** num_months - 1
    
    return (principal_dec * numerator / denominator).quantize(Decimal('0.01'))


def calculate_penalty_accrual(due_date, days_overdue, penalty_rules):
    """
    Calculate accrued penalties based on overdue days and penalty rules.
    
    Args:
        due_date: datetime.date - payment due date
        days_overdue: int - number of days overdue (0 if not overdue)
        penalty_rules: list - list of dicts with 'name' and 'penalty_amount'
    
    Returns:
        Decimal - total penalty accrued
    """
    if days_overdue <= 0:
        return Decimal('0')
    
    total_penalty = Decimal('0')
    
    for rule in penalty_rules:
        penalty_amount = Decimal(str(rule.get('penalty_amount', 0)))
        # Simple approach: apply penalty if overdue by at least 1 day
        if days_overdue > 0:
            total_penalty += penalty_amount
    
    return total_penalty


def get_days_overdue(due_date, today=None):
    """
    Calculate number of days overdue.
    
    Args:
        due_date: datetime.date - payment due date
        today: datetime.date - current date (defaults to today)
    
    Returns:
        int - number of days overdue (0 if not overdue)
    """
    if today is None:
        today = date.today()
    
    if due_date >= today:
        return 0
    
    return (today - due_date).days
