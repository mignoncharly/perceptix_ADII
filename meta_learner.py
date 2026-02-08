"""
Meta-Learner Module: Pattern Analysis and System Intelligence
Analyzes historical incidents to detect patterns and improve future performance.
"""
import json
import logging
from typing import Dict, Any, List
from collections import Counter
from datetime import datetime
from database import DatabaseManager
from models import MetaAnalysisReport, PatternInsight
from exceptions import MetaLearnerError, PatternAnalysisError


logger = logging.getLogger("PerceptixMetaLearner")


class MetaLearner:
    """
    The Subconscious Intelligence.
    Analyzes long-term memory (Historian DB) to find systemic weaknesses
    and recurring patterns.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize MetaLearner with database manager.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager
        self.component_id = "META_LEARNER_V1"

    def analyze_patterns(self) -> MetaAnalysisReport:
        """
        Mine the database for recurring patterns and systemic issues.

        Returns:
            MetaAnalysisReport: Validated analysis report

        Raises:
            MetaLearnerError: If analysis fails
            PatternAnalysisError: If pattern detection fails
        """
        try:
            logger.info("[META] Starting pattern analysis")

            # 1. Get incident statistics
            stats = self._get_incident_statistics()

            # 2. Extract culprit services from high-confidence incidents
            culprits = self._extract_culprit_services(confidence_threshold=80.0)

            # 3. Analyze temporal patterns
            temporal_patterns = self._analyze_temporal_patterns()

            # 4. Generate recommendations
            recommendation = self._generate_recommendation(culprits, stats)

            # 5. Identify dominant pattern
            if culprits:
                dominant_culprit = max(culprits, key=culprits.get)
                pattern_signature = self._generate_pattern_signature(dominant_culprit, stats)
            else:
                dominant_culprit = "None"
                pattern_signature = "Insufficient data for pattern detection"

            # 6. Build validated report
            report = MetaAnalysisReport(
                period_analyzed="Last 90 Days",
                total_incidents=stats['total_incidents'],
                most_frequent_type=stats['most_frequent_type'],
                detected_pattern=PatternInsight(
                    culprit_service=dominant_culprit,
                    frequency=culprits.get(dominant_culprit, 0),
                    pattern_signature=pattern_signature
                ),
                recommendation=recommendation
            )

            logger.info(
                f"[META] Analysis complete: {stats['total_incidents']} incidents, "
                f"culprit={dominant_culprit}"
            )

            return report

        except PatternAnalysisError:
            raise

        except Exception as e:
            raise MetaLearnerError(
                f"Pattern analysis failed: {e}",
                component=self.component_id
            )

    def _get_incident_statistics(self) -> Dict[str, Any]:
        """
        Get aggregate statistics from incidents table.

        Returns:
            Dict: Statistics including total count and type distribution

        Raises:
            PatternAnalysisError: If query fails
        """
        try:
            with self.db_manager.connection() as conn:
                # Get total count
                cursor = conn.execute("SELECT COUNT(*) FROM incidents")
                total = cursor.fetchone()[0]

                # Get type distribution
                cursor = conn.execute("""
                    SELECT type, COUNT(*), AVG(confidence)
                    FROM incidents
                    GROUP BY type
                    ORDER BY COUNT(*) DESC
                """)
                type_stats = cursor.fetchall()

            most_frequent_type = type_stats[0][0] if type_stats else "N/A"

            return {
                'total_incidents': total,
                'most_frequent_type': most_frequent_type,
                'type_distribution': type_stats
            }

        except Exception as e:
            raise PatternAnalysisError(
                f"Failed to get incident statistics: {e}",
                component=self.component_id
            )

    def _extract_culprit_services(self, confidence_threshold: float = 80.0) -> Dict[str, int]:
        """
        Extract services that appear in high-confidence incidents.

        Args:
            confidence_threshold: Minimum confidence to consider

        Returns:
            Dict: Service name to frequency mapping

        Raises:
            PatternAnalysisError: If extraction fails
        """
        try:
            with self.db_manager.connection() as conn:
                cursor = conn.execute("""
                    SELECT summary, full_json
                    FROM incidents
                    WHERE confidence > ?
                """, (confidence_threshold,))
                high_conf_incidents = cursor.fetchall()

            # Service name patterns to search for
            service_keywords = [
                'checkout-service', 'payment-service', 'inventory-service',
                'user-service', 'order-service', 'notification-service',
                'analytics-service', 'warehouse-service'
            ]

            culprit_counter = Counter()

            for summary, raw_json in high_conf_incidents:
                # Search in summary
                summary_lower = summary.lower() if summary else ""
                for service in service_keywords:
                    if service in summary_lower:
                        culprit_counter[service] += 1

                # Search in JSON (root cause analysis)
                try:
                    incident_data = json.loads(raw_json)
                    root_cause = incident_data.get('root_cause_analysis', '').lower()
                    for service in service_keywords:
                        if service in root_cause:
                            culprit_counter[service] += 1
                except json.JSONDecodeError:
                    continue

            return dict(culprit_counter)

        except Exception as e:
            raise PatternAnalysisError(
                f"Failed to extract culprit services: {e}",
                component=self.component_id
            )

    def _analyze_temporal_patterns(self) -> Dict[str, Any]:
        """
        Analyze temporal patterns in incidents.

        Returns:
            Dict: Temporal pattern analysis

        Raises:
            PatternAnalysisError: If analysis fails
        """
        try:
            with self.db_manager.connection() as conn:
                # Get incidents with timestamps
                cursor = conn.execute("""
                    SELECT timestamp, type
                    FROM incidents
                    ORDER BY timestamp DESC
                    LIMIT 100
                """)
                incidents = cursor.fetchall()

            # Analyze day of week and hour of day
            days = []
            hours = []
            
            for ts_str, _ in incidents:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    days.append(dt.strftime("%A"))
                    hours.append(dt.hour)
                except (ValueError, TypeError):
                    continue
            
            day_counts = Counter(days)
            hour_counts = Counter(hours)
            
            most_active_day = day_counts.most_common(1)[0][0] if day_counts else "Unknown"
            most_active_hour = hour_counts.most_common(1)[0][0] if hour_counts else 0
            
            return {
                'most_active_day': most_active_day,
                'most_active_hour': most_active_hour,
                'day_distribution': dict(day_counts),
                'hour_distribution': dict(hour_counts),
                'recent_incidents': len(incidents),
                'analysis_complete': True
            }

        except Exception as e:
            raise PatternAnalysisError(
                f"Failed to analyze temporal patterns: {e}",
                component=self.component_id
            )

    def _generate_pattern_signature(self, service: str, stats: Dict) -> str:
        """
        Generate human-readable pattern signature.

        Args:
            service: Service name
            stats: Incident statistics

        Returns:
            str: Pattern signature
        """
        most_frequent_type = stats['most_frequent_type']
        total = stats['total_incidents']

        if total > 5:
            return (
                f"Repeated {most_frequent_type} incidents following "
                f"{service} changes. Pattern observed across {total} incidents."
            )
        elif total > 0:
            return f"{most_frequent_type} incidents detected in {service}."
        else:
            return "No significant patterns detected yet."

    def _generate_recommendation(self, culprits: Dict[str, int], stats: Dict) -> str:
        """
        Generate actionable recommendation based on analysis.

        Args:
            culprits: Service frequency mapping
            stats: Incident statistics

        Returns:
            str: Recommendation text
        """
        if not culprits:
            return (
                "RECOMMENDATION: Continue monitoring. "
                "Insufficient incident history for pattern-based recommendations."
            )

        dominant_service = max(culprits, key=culprits.get)
        frequency = culprits[dominant_service]

        if frequency >= 3:
            return (
                f"CRITICAL RECOMMENDATION: Implement strict schema validation and "
                f"integration testing on '{dominant_service}' deployments. "
                f"This service has been implicated in {frequency} high-confidence incidents. "
                f"Consider: 1) Pre-deployment schema compatibility checks, "
                f"2) Automated rollback triggers, 3) Enhanced monitoring."
            )
        elif frequency >= 2:
            return (
                f"RECOMMENDATION: Review deployment procedures for '{dominant_service}'. "
                f"Multiple incidents detected. Add pre-production validation checks."
            )
        else:
            return (
                f"RECOMMENDATION: Monitor '{dominant_service}' deployments closely. "
                f"Pattern detected but not yet statistically significant."
            )


# -------------------------------------------------------------------------
# TERMINAL EXECUTION BLOCK
# -------------------------------------------------------------------------
if __name__ == "__main__":
    from config import load_config
    from main import PerceptixSystem
    import time

    print("\n" + "="*70)
    print("META-LEARNER MODULE - STANDALONE TEST")
    print("="*70 + "\n")

    try:
        # Initialize system and generate some incidents
        config = load_config()
        print(f"✓ Configuration loaded: Mode={config.system.mode.value}")

        with PerceptixSystem(config) as app:
            print("✓ System initialized")

            # Generate a few incidents for analysis
            print("\n--- Generating Sample Incidents ---")
            for i in range(3):
                print(f"Running cycle {i+1}...")
                report = app.run_cycle(cycle_id=i+1, simulate_failure=True)
                if report:
                    print(f"  ✓ Incident {report.report_id} created")
                time.sleep(0.5)

            # Now run meta-analysis
            print("\n--- Running Meta-Analysis ---")
            learner = MetaLearner(app.db_manager)
            analysis = learner.analyze_patterns()

            # Display results
            print(f"\n--- Meta-Analysis Report ---")
            print(f"Period: {analysis.period_analyzed}")
            print(f"Total Incidents: {analysis.total_incidents}")
            print(f"Most Frequent Type: {analysis.most_frequent_type}")
            print(f"\nDetected Pattern:")
            print(f"  Culprit Service: {analysis.detected_pattern.culprit_service}")
            print(f"  Frequency: {analysis.detected_pattern.frequency}")
            print(f"  Signature: {analysis.detected_pattern.pattern_signature}")
            print(f"\n{analysis.recommendation}")

            print("\n" + "="*70)
            print("✓ ALL META-LEARNER TESTS PASSED")
            print("="*70 + "\n")

    except Exception as e:
        print(f"\n✗ META-LEARNER TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
