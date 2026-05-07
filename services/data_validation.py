"""
Data validation service – Python translation of backend/src/services/data-validation.js.
All 4 rules and all field-level checks are preserved.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import pandas as pd

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', re.IGNORECASE)


def _text(val) -> str:
    if val is None:
        return ''
    if isinstance(val, float) and (val != val):  # NaN
        return ''
    return str(val).strip()


def _upper(val) -> str:
    return _text(val).upper()


def _has_value(val) -> bool:
    return _text(val) != ''


def _parse_excel_date(val) -> Optional[int]:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return int(f)
    except (TypeError, ValueError):
        pass
    if _has_value(val):
        try:
            d = datetime.fromisoformat(str(val))
            return int((d - datetime(1899, 12, 30)).days)
        except ValueError:
            pass
    return None


def _excel_to_datetime(serial: int) -> datetime:
    return datetime(1899, 12, 30) + timedelta(days=serial)


def _iso_week_key(serial: int) -> str:
    dt = _excel_to_datetime(serial)
    return f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"


class DataValidationService:
    def __init__(self, raw_data: Dict[str, pd.DataFrame]):
        self.userdata: pd.DataFrame = raw_data.get('userdata', pd.DataFrame())
        self.timecards: pd.DataFrame = raw_data.get('timecardactuals', pd.DataFrame())

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _canonical_user_key(self, row) -> str:
        return _upper(row.get('Name') or row.get('Email address'))

    def _canonical_tc_key(self, row) -> str:
        return _upper(row.get('resource_email'))

    def _get_user_resource_id(self, row) -> str:
        return _text(row.get('Employee ID') or row.get('External ID') or row.get('Name'))

    def _get_tc_resource_id(self, row) -> str:
        return _text(
            row.get('resource_id') or row.get('resource_id_onb') or
            row.get('bl_employee_id') or row.get('resource_email')
        )

    def _build_issue(self, issue_type, sheet, row_number, resource_key, message, record=None):
        return {
            'type': issue_type,
            'sheet': sheet,
            'rowNumber': row_number,
            'resourceKey': resource_key,
            'message': message,
            'record': record or {},
        }

    # ------------------------------------------------------------------ #
    #  Field-level issues                                                  #
    # ------------------------------------------------------------------ #

    def _build_field_issues(self) -> List[Dict]:
        issues = []

        for idx, row in self.userdata.iterrows():
            row_number = idx + 2
            canonical = self._canonical_user_key(row)
            resource_id = self._get_user_resource_id(row)
            division = _text(row.get('Division'))
            rw_type = _text(row.get('Resource Work Types'))
            onboard = _text(row.get('User Onboarding Date'))
            raw_name = _text(row.get('Name'))

            if not _has_value(resource_id):
                issues.append(self._build_issue(
                    'missing_resource_id', 'Userdata', row_number, canonical,
                    'resource_id proxy is blank in Userdata',
                    {'name': raw_name, 'employeeId': row.get('Employee ID')}
                ))
            if not _has_value(division):
                issues.append(self._build_issue(
                    'missing_division', 'Userdata', row_number, canonical,
                    'Division is blank in Userdata', {'name': raw_name}
                ))
            if not _has_value(rw_type):
                issues.append(self._build_issue(
                    'missing_resource_work_type', 'Userdata', row_number, canonical,
                    'Resource Work Type is blank in Userdata', {'name': raw_name}
                ))
            if not _has_value(onboard):
                issues.append(self._build_issue(
                    'missing_onboarding_date', 'Userdata', row_number, canonical,
                    'User Onboarding Date is blank in Userdata', {'name': raw_name}
                ))
            if not _EMAIL_RE.match(raw_name):
                issues.append(self._build_issue(
                    'invalid_userdata_email', 'Userdata', row_number, canonical,
                    'Name does not contain a valid email address in Userdata',
                    {'name': raw_name}
                ))

        for idx, row in self.timecards.iterrows():
            row_number = idx + 2
            canonical = self._canonical_tc_key(row)
            resource_id = self._get_tc_resource_id(row)
            email = _text(row.get('resource_email'))
            project = _text(row.get('project'))
            load = row.get('load')
            tc_date = row.get('tc_date')

            if not _has_value(resource_id):
                issues.append(self._build_issue(
                    'missing_resource_id', 'Timecardactuals', row_number, canonical,
                    'resource_id is blank in Timecardactuals', {'resourceEmail': email}
                ))
            if not _EMAIL_RE.match(email):
                issues.append(self._build_issue(
                    'invalid_timecard_email', 'Timecardactuals', row_number, canonical,
                    'resource_email does not contain a valid email address',
                    {'resourceEmail': email}
                ))
            if not _has_value(project):
                issues.append(self._build_issue(
                    'blank_project', 'Timecardactuals', row_number, canonical,
                    'project is blank in Timecardactuals', {'resourceEmail': email}
                ))
            if not _has_value(load):
                issues.append(self._build_issue(
                    'blank_load', 'Timecardactuals', row_number, canonical,
                    'load is blank in Timecardactuals', {'resourceEmail': email, 'project': project}
                ))
            if not _has_value(tc_date):
                issues.append(self._build_issue(
                    'blank_tc_date', 'Timecardactuals', row_number, canonical,
                    'tc_date is blank in Timecardactuals', {'resourceEmail': email, 'project': project}
                ))

        return issues

    # ------------------------------------------------------------------ #
    #  Main validation                                                     #
    # ------------------------------------------------------------------ #

    def validate(self) -> Dict:
        # Build resource profile map from userdata
        profiles: Dict[str, Dict] = {}
        for idx, row in self.userdata.iterrows():
            key = self._canonical_user_key(row)
            if not key:
                continue
            div = _text(row.get('Division')) or 'Unknown'
            loc = _text(row.get('Location (Entra)')) or 'Unknown'
            rw_type = _text(row.get('Resource Work Types')) or 'Unknown'
            name = _text(row.get('Description')) or 'Unknown'
            onboard = _text(row.get('User Onboarding Date'))
            inactive = _upper(row.get('Inactive')) == 'YES'
            resource_id = self._get_user_resource_id(row)

            if key not in profiles:
                profiles[key] = {
                    'canonicalKey': key,
                    'resourceId': resource_id,
                    'name': name,
                    'division': div,
                    'location': loc,
                    'resourceWorkType': rw_type,
                    'onboardingDate': onboard,
                    'inactiveFlag': inactive,
                    'rowNumbers': [idx + 2],
                    'divisions': {div},
                    'locations': {loc},
                    'resourceWorkTypes': {rw_type},
                    'names': {name},
                }
            else:
                p = profiles[key]
                p['rowNumbers'].append(idx + 2)
                p['divisions'].add(div)
                p['locations'].add(loc)
                p['resourceWorkTypes'].add(rw_type)
                p['names'].add(name)
                if not p['resourceId']:
                    p['resourceId'] = resource_id
                if not _has_value(p['onboardingDate']):
                    p['onboardingDate'] = onboard
                p['inactiveFlag'] = p['inactiveFlag'] or inactive

        # Scan timecards
        timecards_by_key: Dict[str, int] = {}
        weekly_hours_by_key: Dict[str, Dict[str, float]] = {}
        offboard_by_key: Dict[str, int] = {}
        tc_resource_id_counts: Dict[str, int] = {}
        orphan_timecards: List[Dict] = []

        for idx, row in self.timecards.iterrows():
            key = self._canonical_tc_key(row)
            row_number = idx + 2
            resource_id = self._get_tc_resource_id(row)
            offboard = row.get('offboard_date')
            excel_date = _parse_excel_date(row.get('tc_date'))
            load = 0.0
            try:
                load = float(row.get('load') or 0)
            except (TypeError, ValueError):
                pass

            if resource_id:
                tc_resource_id_counts[resource_id] = tc_resource_id_counts.get(resource_id, 0) + 1

            if not key:
                continue

            timecards_by_key[key] = timecards_by_key.get(key, 0) + 1

            if excel_date is not None:
                wk = _iso_week_key(excel_date)
                weekly_hours_by_key.setdefault(key, {})
                weekly_hours_by_key[key][wk] = weekly_hours_by_key[key].get(wk, 0.0) + load

            if offboard is not None:
                try:
                    offboard_serial = int(float(offboard))
                    if offboard_serial > 0:
                        offboard_by_key[key] = offboard_serial
                except (TypeError, ValueError):
                    pass

            if key not in profiles:
                orphan_timecards.append({
                    'resourceKey': key,
                    'rowNumber': row_number,
                    'resourceEmail': _text(row.get('resource_email')),
                    'project': _text(row.get('project')),
                })

        # Summarise per profile
        field_issues = self._build_field_issues()

        dup_names: Dict[str, List] = {}
        multi_division: List[Dict] = []
        inconsistent_records: List[Dict] = []
        resources_by_location: Dict[str, int] = {}
        resources_by_division: Dict[str, int] = {}
        resources_by_location_and_division: Dict[str, Dict[str, int]] = {}
        resources_by_division_and_status: Dict[str, Dict[str, int]] = {}
        zero_timesheet: List[Dict] = []
        active_resources = 0
        inactive_resources = 0
        resources_meeting_threshold = 0
        resources_missing_threshold = 0
        resources_with_onboarding = 0
        inactive_flag_mismatch = 0

        tc_resource_id_duplicates = [
            {'resourceId': rid, 'count': cnt}
            for rid, cnt in tc_resource_id_counts.items() if cnt > 1
        ]
        tc_resource_id_duplicates.sort(key=lambda x: -x['count'])

        for key, profile in profiles.items():
            primary_name = next(iter(profile['names'])) or 'Unknown'
            primary_div = next(iter(profile['divisions'])) or 'Unknown'
            primary_loc = next(iter(profile['locations'])) or 'Unknown'
            primary_type = next(iter(profile['resourceWorkTypes'])) or 'Unknown'

            resources_by_location[primary_loc] = resources_by_location.get(primary_loc, 0) + 1
            resources_by_division[primary_div] = resources_by_division.get(primary_div, 0) + 1
            resources_by_location_and_division.setdefault(primary_loc, {})[primary_div] = \
                resources_by_location_and_division.get(primary_loc, {}).get(primary_div, 0) + 1

            name_upper = primary_name.upper()
            dup_names.setdefault(name_upper, []).append({
                'resourceKey': key, 'resourceName': primary_name, 'division': primary_div})

            if len(profile['divisions']) > 1:
                multi_division.append({
                    'resourceKey': key,
                    'resourceName': primary_name,
                    'divisions': sorted(profile['divisions']),
                    'rowNumbers': profile['rowNumbers'],
                })

            inconsistencies = []
            if len(profile['locations']) > 1:
                inconsistencies.append(f"Multiple locations: {', '.join(sorted(profile['locations']))}")
            if len(profile['resourceWorkTypes']) > 1:
                inconsistencies.append(f"Multiple resource work types: {', '.join(sorted(profile['resourceWorkTypes']))}")
            if len(profile['names']) > 1:
                inconsistencies.append(f"Multiple names: {', '.join(sorted(profile['names']))}")

            has_offboard = key in offboard_by_key
            status_bucket = 'Inactive' if has_offboard else 'Active'
            if has_offboard:
                inactive_resources += 1
            else:
                active_resources += 1

            resources_by_division_and_status.setdefault(primary_div, {'Active': 0, 'Inactive': 0})
            resources_by_division_and_status[primary_div][status_bucket] += 1

            if profile['inactiveFlag'] and not has_offboard:
                inactive_flag_mismatch += 1
                inconsistencies.append('Inactive flag is YES but no offboard_date exists in Timecardactuals')

            if _has_value(profile['onboardingDate']):
                resources_with_onboarding += 1

            tc_count = timecards_by_key.get(key, 0)
            wk_map = weekly_hours_by_key.get(key, {})
            meets_threshold = any(h >= 40 for h in wk_map.values()) if wk_map else False

            if meets_threshold:
                resources_meeting_threshold += 1
            else:
                resources_missing_threshold += 1

            if tc_count == 0:
                zero_timesheet.append({
                    'resourceKey': key,
                    'resourceName': primary_name,
                    'division': primary_div,
                    'location': primary_loc,
                })

            if inconsistencies:
                inconsistent_records.append({
                    'resourceKey': key,
                    'resourceName': primary_name,
                    'division': primary_div,
                    'location': primary_loc,
                    'issues': inconsistencies,
                })

            # Update profile with derived fields
            profile.update({
                'name': primary_name,
                'division': primary_div,
                'location': primary_loc,
                'resourceWorkType': primary_type,
                'hasOffboardDate': has_offboard,
                'timecardCount': tc_count,
                'meetsFortyHourWeekThreshold': meets_threshold,
            })

        dup_name_violations = [
            {'resourceName': recs[0]['resourceName'], 'count': len(recs), 'records': recs}
            for recs in dup_names.values() if len(recs) > 1
        ]
        dup_name_violations.sort(key=lambda x: -x['count'])

        all_issues = (
            field_issues
            + [self._build_issue('zero_timesheet_entries', 'Derived', None,
                                 item['resourceKey'],
                                 'Resource has zero timesheet entries', item)
               for item in zero_timesheet]
            + [self._build_issue('inconsistent_record', 'Derived', None,
                                 item['resourceKey'],
                                 ' | '.join(item['issues']), item)
               for item in inconsistent_records]
            + [self._build_issue('orphan_timecard_record', 'Timecardactuals',
                                 item['rowNumber'], item['resourceKey'],
                                 'Timecard record does not match any Userdata resource', item)
               for item in orphan_timecards]
        )

        total_resources = len(profiles)
        total_records = len(self.userdata) + len(self.timecards)
        valid_pct = max(0, round(
            (total_records - len(all_issues)) / total_records * 100, 2
        )) if total_records > 0 else 0.0

        rules = [
            {
                'id': 'one-resource-one-division',
                'label': 'Rule 1: One resource -> one division',
                'status': 'PASS' if len(multi_division) == 0 else 'FAIL',
                'violationCount': len(multi_division),
                'sample': multi_division[:10],
                'definition': {
                    'title': 'One resource -> one division',
                    'description': 'Each resource should be assigned to only one division.',
                },
            },
            {
                'id': 'no-duplicate-names',
                'label': 'Rule 2: No duplicate names',
                'status': 'PASS' if len(dup_name_violations) == 0 else 'FAIL',
                'violationCount': len(dup_name_violations),
                'sample': dup_name_violations[:10],
                'definition': {
                    'title': 'No duplicate resource names',
                    'description': 'Resource names must be unique to avoid ambiguity.',
                },
            },
            {
                'id': 'required-fields-not-null',
                'label': 'Rule 3: Required fields not null',
                'status': 'PASS' if len(field_issues) == 0 else 'FAIL',
                'violationCount': len(field_issues),
                'sample': field_issues[:10],
                'definition': {
                    'title': 'Required fields are not null',
                    'description': 'All critical fields must have values for records to be usable.',
                },
            },
            {
                'id': 'all-resources-have-onboarding-date',
                'label': 'Rule 4: All resources have an onboarding date',
                'status': 'PASS' if resources_with_onboarding == total_resources else 'FAIL',
                'violationCount': total_resources - resources_with_onboarding,
                'sample': [
                    {'resourceKey': p['canonicalKey'], 'resourceName': p['name'], 'division': p['division']}
                    for p in profiles.values() if not _has_value(p['onboardingDate'])
                ][:10],
                'definition': {
                    'title': 'All resources have onboarding date',
                    'description': 'Every resource should have a documented onboarding date.',
                },
            },
        ]

        summary_status = 'VALID' if all(r['status'] == 'PASS' for r in rules) else 'NOT VALID'
        invalidation_reasons = []
        for r in rules:
            if r['status'] == 'FAIL':
                reason_map = {
                    'one-resource-one-division': f"{len(multi_division)} resources assigned to multiple divisions",
                    'no-duplicate-names': f"{len(dup_name_violations)} resource name duplicates detected",
                    'required-fields-not-null': f"{len(field_issues)} records have missing required fields",
                    'all-resources-have-onboarding-date': f"{total_resources - resources_with_onboarding} resources missing onboarding dates",
                }
                invalidation_reasons.append({
                    'rule': r['id'],
                    'label': r['label'],
                    'reason': reason_map.get(r['id'], ''),
                    'count': r['violationCount'],
                })

        # Violation type breakdown
        violation_breakdown: Dict[str, int] = {}
        issues_by_division: Dict[str, int] = {}
        for issue in all_issues:
            t = issue.get('type') or 'unknown'
            violation_breakdown[t] = violation_breakdown.get(t, 0) + 1
            div = (issue.get('record') or {}).get('division') or \
                  profiles.get(issue.get('resourceKey') or '', {}).get('division') or 'Unknown'
            issues_by_division[div] = issues_by_division.get(div, 0) + 1

        resource_inventory = [
            {
                'resourceKey': p['canonicalKey'],
                'resourceName': p['name'],
                'division': p['division'],
                'location': p['location'],
                'resourceWorkType': p['resourceWorkType'],
                'status': 'Inactive' if p.get('hasOffboardDate') else 'Active',
                'onboardingDate': p['onboardingDate'] if _has_value(p['onboardingDate']) else None,
                'timecardCount': p.get('timecardCount', 0),
                'meetsFortyHourWeekThreshold': p.get('meetsFortyHourWeekThreshold', False),
                'issueCount': sum(1 for iss in all_issues if iss.get('resourceKey') == p['canonicalKey']),
            }
            for p in profiles.values()
        ]

        return {
            'metadata': {
                'totalUserdataRows': len(self.userdata),
                'totalTimecardRows': len(self.timecards),
                'resourceJoinKey': 'Userdata.Name ↔ Timecardactuals.resource_email',
            },
            'kpis': {
                'totalResources': total_resources,
                'validRecordPct': valid_pct,
                'issuesFound': len(all_issues),
            },
            'metrics': {
                'totalDistinctResourcesGlobal': total_resources,
                'totalDistinctResourcesByLocation': resources_by_location,
                'totalResourcesPerDivision': resources_by_division,
                'activeResources': active_resources,
                'inactiveResources': inactive_resources,
                'resourcesAppearingInTimesheets': resources_meeting_threshold,
                'resourcesNotAppearingInTimesheets': resources_missing_threshold,
                'capacityFoundation': {
                    'totalResourcesProxyForCapacity': total_resources,
                    'resourcesWithOnboardingDate': resources_with_onboarding,
                    'resourcesMissingOnboardingDate': total_resources - resources_with_onboarding,
                },
            },
            'analytics': {
                'resourcesByLocationAndDivision': resources_by_location_and_division,
                'resourcesByDivisionAndStatus': resources_by_division_and_status,
                'issuesByDivision': issues_by_division,
                'resourceInventory': resource_inventory,
            },
            'checks': {
                'duplicateResourceIdCheck': {
                    'count': len(tc_resource_id_duplicates),
                    'sample': tc_resource_id_duplicates[:10],
                },
                'multipleDivisionAssignments': {
                    'count': len(multi_division),
                    'sample': multi_division[:10],
                },
                'zeroTimesheetEntries': {
                    'count': len(zero_timesheet),
                    'sample': zero_timesheet[:10],
                },
                'inconsistentRecords': {
                    'count': len(inconsistent_records),
                    'sample': inconsistent_records[:10],
                },
                'orphanTimecardRecords': {
                    'count': len(orphan_timecards),
                    'sample': orphan_timecards[:10],
                },
                'inactiveFlagMismatchCount': inactive_flag_mismatch,
            },
            'rules': rules,
            'issues': all_issues,
            'violationTypeBreakdown': violation_breakdown,
            'summary': {
                'status': summary_status,
                'statement': (
                    'Data is VALID for further analysis'
                    if summary_status == 'VALID'
                    else 'Data is NOT VALID for further analysis'
                ),
                'invalidationReasons': invalidation_reasons,
            },
        }

    # ------------------------------------------------------------------ #
    #  Q&A                                                                 #
    # ------------------------------------------------------------------ #

    def answer_question(self, question: str, validation: Dict) -> str:
        """Static pattern-matching Q&A – mirrors answerQuestion() in JS."""
        q = question.lower().strip()
        if not q:
            return 'Ask about total resources, duplicate resources, multiple divisions, or data quality issues.'

        metrics = validation.get('metrics', {})
        analytics = validation.get('analytics', {})
        checks = validation.get('checks', {})
        kpis = validation.get('kpis', {})

        locations = list((metrics.get('totalDistinctResourcesByLocation') or {}).keys())
        divisions = list((metrics.get('totalResourcesPerDivision') or {}).keys())

        loc_match = self._find_dimension_match(question, locations)
        div_match = self._find_dimension_match(question, divisions)

        if ('how many' in q or 'count' in q) and loc_match and div_match:
            count = (analytics.get('resourcesByLocationAndDivision') or {}) \
                .get(loc_match, {}).get(div_match, 0)
            return f"{count} resources are in {loc_match} and {div_match}."

        if ('which division' in q or 'what division' in q) and 'most' in q and 'issue' in q:
            issues_by_div = analytics.get('issuesByDivision') or {}
            if issues_by_div:
                top = max(issues_by_div.items(), key=lambda x: x[1])
                return f"{top[0]} has the most data quality issues with {top[1]} issues."

        if ('status' in q or 'active' in q or 'inactive' in q) and div_match:
            counts = (analytics.get('resourcesByDivisionAndStatus') or {}).get(div_match)
            if counts:
                return (f"{div_match} has {counts.get('Active', 0)} active "
                        f"and {counts.get('Inactive', 0)} inactive resources.")

        if 'distinct resource' in q or 'total resource' in q:
            return f"There are {metrics.get('totalDistinctResourcesGlobal', 0)} distinct resources."

        if 'duplicate resource' in q:
            cnt = (checks.get('duplicateResourceIdCheck') or {}).get('count', 0)
            return (f"Yes. {cnt} duplicate resource_id values were found."
                    if cnt > 0 else "No duplicate resource_id values were found.")

        if 'multiple division' in q or 'belong to multiple' in q:
            cnt = (checks.get('multipleDivisionAssignments') or {}).get('count', 0)
            return (f"Yes. {cnt} resources appear in multiple divisions."
                    if cnt > 0 else "No. Each resource is assigned to a single division.")

        if 'quality issue' in q or ' issue' in q:
            total = kpis.get('issuesFound', 0)
            status = validation.get('summary', {}).get('status', 'UNKNOWN')
            return f"There are {total} total data quality issues. Overall status is {status}."

        if 'not appearing in timesheets' in q or 'missing timesheets' in q:
            cnt = metrics.get('resourcesNotAppearingInTimesheets', 0)
            return f"{cnt} resources do not meet the minimum 40-hours-per-week timesheet threshold."

        return ('Question not recognized. Try asking about: total resources, '
                'duplicate resources, multiple divisions, resources missing timesheets, '
                'or data quality issues.')

    def _find_dimension_match(self, question: str, options: list) -> Optional[str]:
        """Fuzzy match a dimension value in the question string."""
        def normalise(s):
            s = s.lower()
            s = re.sub(r'[&+]', ' and ', s)
            s = re.sub(r'[^a-z0-9\s]', ' ', s)
            s = re.sub(r'\bdivision\b', ' ', s)
            s = re.sub(r'\bresources?\b', ' ', s)
            return re.sub(r'\s+', ' ', s).strip()

        nq = normalise(question)
        best_match = None
        best_score = 0

        for opt in options:
            nopt = normalise(opt)
            if not nopt:
                continue
            if nopt in nq:
                score = len(nopt) + 100
                if score > best_score:
                    best_match = opt
                    best_score = score
                continue
            tokens = nopt.split()
            if not tokens:
                continue
            matched = sum(1 for t in tokens if t in nq)
            score = matched / len(tokens)
            if score >= 0.6 and score > best_score:
                best_match = opt
                best_score = score

        return best_match

    def ask_with_groq(self, question: str, validation: Dict, groq_api_key: str) -> str:
        """Call Groq API for richer answers; falls back to static Q&A on failure."""
        if not groq_api_key or not question.strip():
            return self.answer_question(question, validation)

        import requests
        metrics = validation.get('metrics', {})
        kpis = validation.get('kpis', {})
        analytics = validation.get('analytics', {})
        summary = validation.get('summary', {})

        context = f"""
DATASET OVERVIEW:
  Total Distinct Resources: {kpis.get('totalResources', 0)}
  Valid Records: {kpis.get('validRecordPct', 0)}%
  Data Quality Issues: {kpis.get('issuesFound', 0)}
  Active Resources: {metrics.get('activeResources', 0)}
  Inactive Resources: {metrics.get('inactiveResources', 0)}
  Resources meeting 40h/week: {metrics.get('resourcesAppearingInTimesheets', 0)}
  Resources not meeting 40h/week: {metrics.get('resourcesNotAppearingInTimesheets', 0)}
  Validation Status: {summary.get('status', 'UNKNOWN')}

RESOURCES BY LOCATION:
{chr(10).join(f'  {loc}: {cnt}' for loc, cnt in (metrics.get('totalDistinctResourcesByLocation') or {}).items())}

RESOURCES BY DIVISION:
{chr(10).join(f'  {div}: {cnt}' for div, cnt in (metrics.get('totalResourcesPerDivision') or {}).items())}
"""
        system = (
            "You are a data analyst expert in workforce capacity planning. "
            "Answer questions about the dataset concisely (1-3 sentences). "
            "Be specific with numbers."
        )

        for model in ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant']:
            try:
                resp = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {groq_api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': model,
                        'messages': [
                            {'role': 'system', 'content': system},
                            {'role': 'user', 'content': f"{context}\n\nQUESTION: {question}"},
                        ],
                        'max_tokens': 400,
                        'temperature': 0.2,
                    },
                    timeout=15,
                )
                if resp.ok:
                    answer = resp.json()['choices'][0]['message']['content']
                    return answer.strip()
                err = resp.json()
                if (err.get('error') or {}).get('code') != 'model_decommissioned':
                    break
            except Exception:
                break

        return self.answer_question(question, validation)
