"""
Business assumptions – direct Python translation of backend/src/config/assumptions.js.
All 21 assumptions are preserved verbatim.
"""

ASSUMPTIONS = [
    {
        'id': 'data_source',
        'category': 'Data Source',
        'assumption': 'Excel File as Source of Truth',
        'description': 'All employee timecard and capacity data is sourced from the uploaded Excel file. The file is treated as the single source of truth for all calculations.',
        'businessImpact': 'Ensures consistency and traceability of all analysis results to original data',
    },
    {
        'id': 'division_history_r_and_d',
        'category': 'Data Source',
        'assumption': 'Division R&D Renamed to Executive',
        'description': 'The division formerly known as R&D has been renamed to Executive in the current data structure. Historical data may contain references to R&D, but all current analysis uses the Executive division name.',
        'businessImpact': 'Ensures consistent division naming and tracking across the analysis period',
    },
    {
        'id': 'resource_work_type_mapping',
        'category': 'Data Source',
        'assumption': 'Resource Work Type Manually Mapped from Division and Title',
        'description': 'The "Resource Work Type" column (e.g., Clinical Analyst, Vision Engineer, Pharma Scientist) was manually created by combining division and job title information. When a job title had fewer than 4 resources, it was consolidated into a related resource type to ensure meaningful category sizes.',
        'businessImpact': 'Enables accurate resource classification for work type-based capacity analysis and prevents skewed reporting from singleton categories',
    },
    {
        'id': 'resource_allocation',
        'category': 'Resource Allocation',
        'assumption': 'One Division per Resource',
        'description': 'Each employee is assigned to exactly one division. An employee cannot be split across multiple divisions.',
        'businessImpact': 'Ensures clear accountability and prevents double-counting of resource capacity',
    },
    {
        'id': 'work_categorization',
        'category': 'Work Categorization',
        'assumption': 'Two Work Categories',
        'description': 'All work is categorized into two types: (1) Admin & Leave (non-billable overhead), and (2) Billable/Productive Work. Admin includes administrative tasks and leave time.',
        'businessImpact': 'Allows clear separation of overhead costs from billable work for accurate utilization metrics',
    },
    {
        'id': 'capacity_horizon',
        'category': 'Capacity Planning',
        'assumption': 'Capacity Horizon: June 30, 2026',
        'description': 'The target planning date through which active resources are considered. Resources with end dates on or after this date are treated as available for capacity planning.',
        'businessImpact': 'Provides a consistent reference point for workforce capacity forecasting and resource planning',
    },
    {
        'id': 'admin_percent_window',
        'category': 'Admin Percentage Calculation',
        'assumption': 'Rolling 12-Month Window for Admin %',
        'description': 'Admin percentage is calculated using only the most recent 12 months of data (365 days prior to the Capacity Horizon). This excludes historical data beyond 12 months.',
        'businessImpact': 'Reflects current operational realities and removes impact of past anomalies or organizational changes from over a year ago',
    },
    {
        'id': 'admin_percent_per_division',
        'category': 'Admin Percentage Calculation',
        'assumption': 'Per-Division Admin Percentage',
        'description': 'Each division has its own calculated admin percentage based on its specific mix of admin and billable work using the formula: Admin % = (Total Admin + Leave Hours in 12-Month Window / Total Capacity Hours in 12-Month Window) × 100.',
        'businessImpact': "Recognizes that different divisions have different operational overhead patterns, enabling more accurate adjusted capacity calculations specific to each division's actual operational needs",
    },
    {
        'id': 'utilization_formula',
        'category': 'Utilization Metrics',
        'assumption': 'Utilization = Actual Hours / Capacity Hours',
        'description': 'Utilization percentage is calculated as the ratio of actual hours worked to total available capacity hours, expressed as a percentage.',
        'businessImpact': 'Provides standardized metric to measure resource productivity and identify under or over-allocation',
    },
    {
        'id': 'adjusted_capacity_formula',
        'category': 'Adjusted Capacity',
        'assumption': 'Adjusted Capacity = Capacity × (1 - Admin% / 100)',
        'description': 'Adjusted Capacity removes the expected admin overhead from total capacity using the rolling 12-month admin percentage specific to each division.',
        'businessImpact': 'Provides realistic capacity available for billable work by accounting for expected administrative overhead',
    },
    {
        'id': 'quarterly_aggregation',
        'category': 'Time Periods',
        'assumption': 'Quarterly Data Aggregation',
        'description': 'All hours and capacity data are aggregated at the quarterly level (Q3 2025, Q4 2025, Q1 2026, Q2 2026). Finer granularity (daily/weekly) is not aggregated in the main dashboard.',
        'businessImpact': 'Simplifies reporting and focuses on strategic capacity planning at the quarterly business cycle level',
    },
    {
        'id': 'resource_uniqueness',
        'category': 'Data Structure',
        'assumption': 'Resource-Period Uniqueness',
        'description': 'Each row in the aggregated dashboard data represents a unique combination of one resource (employee) and one time period (quarter). A resource cannot appear twice in the same quarter.',
        'businessImpact': 'Ensures accurate count of active resources, proper aggregation of hours, and reliable capacity calculations for quarterly planning',
    },
    {
        'id': 'data_completeness',
        'category': 'Data Quality',
        'assumption': 'Data Completeness and Accuracy',
        'description': 'Key fields required for analysis are expected to be complete and accurate. Missing values in critical fields are treated as zero hours or filtered out.',
        'businessImpact': 'Ensures reliability of utilization and capacity calculations for decision-making',
    },
    {
        'id': 'division_consistency',
        'category': 'Division Data',
        'assumption': 'Consistent Division Structure',
        'description': 'The 7 divisions (Vision Care, Medical & Scientific Affairs, Regulatory Affairs, Clinical Services, Portfolio + Project Management, Pharma/Consumer, Surgical) remain constant throughout the analysis period.',
        'businessImpact': 'Enables consistent comparison of capacity and utilization trends across divisions',
    },
    {
        'id': 'fte_capacity_calculation',
        'category': 'Resource Capacity',
        'assumption': '1 Resource = 1 FTE Per Working Day',
        'description': 'Each resource has a capacity of 1 FTE per working day, regardless of role level or seniority. Capacity hours are calculated as 1 FTE × standard hours per day for each working day.',
        'businessImpact': 'Provides a standardized capacity unit that enables direct comparison of resource utilization across roles',
    },
    {
        'id': 'standard_hours_per_day',
        'category': 'Resource Capacity',
        'assumption': 'Standard Working Hours by Country',
        'description': 'The system has capability for country-specific standard working hours (e.g., 8 for US, 7 for France, 7.5 for Germany). Since the dataset is currently filtered to US resources only, all resources use 8 hours per standard working day.',
        'businessImpact': 'Ensures accurate FTE calculations reflecting local labor laws while maintaining flexibility for future global operations',
    },
    {
        'id': 'us_only_resources',
        'category': 'Resource Filtering',
        'assumption': 'US Resources Only',
        'description': 'Only resources with location marked as "United States" or "United States of America" are included. Resources from other countries are excluded from all calculations.',
        'businessImpact': 'Focuses capacity planning on the primary operational workforce',
    },
    {
        'id': 'excluded_divisions',
        'category': 'Resource Filtering',
        'assumption': 'Excluded Divisions: Safety Vigilance & Executive',
        'description': 'Two divisions are excluded: (1) Safety Vigilance, and (2) Executive. Resources assigned to these divisions are not included in aggregated metrics.',
        'businessImpact': 'Focuses analysis on core operational divisions and excludes governance/safety functions',
    },
    {
        'id': 'working_days_only',
        'category': 'Time Calculations',
        'assumption': 'Working Days Only (Monday–Friday)',
        'description': 'Capacity is calculated only for working days. Weekends and public holidays are excluded.',
        'businessImpact': 'Ensures realistic capacity planning based on actual available working days',
    },
    {
        'id': 'resource_onoffboard_dates',
        'category': 'Resource Filtering',
        'assumption': 'Resource Active Window: Onboard to Offboard Dates',
        'description': "Each resource has an active working window defined by onboard_date and offboard_date fields. Capacity is only calculated within each resource's active window. Resources without offboard dates are projected through the Capacity Horizon.",
        'businessImpact': 'Ensures accurate capacity accounting for employee lifecycle (hires, departures, projections)',
    },
    {
        'id': 'fte_calculation_and_aggregation',
        'category': 'Utilization Metrics',
        'assumption': 'FTE Calculation and Aggregation Across Time Periods',
        'description': 'FTEs are calculated daily as Actual Hours / Standard Hours Per Day (typically 8 for US resources). Daily FTEs are then aggregated to monthly and quarterly totals by summing across all working days in that period.',
        'businessImpact': 'Enables comparison of resource utilization as a standardized FTE metric while preserving total hours for cost analysis',
    },
    {
        'id': 'capacity_regardless_of_actuals',
        'category': 'Resource Capacity',
        'assumption': 'Capacity Calculated Regardless of Timecard Actuals',
        'description': "A resource's capacity is calculated for every working day in their active employment window, whether or not they recorded timecard actuals for that day. If no timecard actual is recorded on a day, the actual hours are treated as 0.",
        'businessImpact': 'Ensures accurate capacity-based metrics even when timecard data is incomplete on specific days',
    },
]


def get_assumptions() -> list:
    return ASSUMPTIONS


def get_assumptions_by_category() -> dict:
    grouped = {}
    for a in ASSUMPTIONS:
        cat = a['category']
        grouped.setdefault(cat, []).append(a)
    return grouped
