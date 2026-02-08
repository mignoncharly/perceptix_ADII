"""
Performance Analysis Script

Analyzes Locust test results and generates reports.
"""

import pandas as pd
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class PerformanceAnalyzer:
    """Analyzes load test results and generates insights."""

    def __init__(self, results_path: str):
        """
        Initialize analyzer.

        Args:
            results_path: Path to Locust stats history CSV or JSON
        """
        self.results_path = Path(results_path)

    def analyze_csv_stats(self) -> Dict[str, Any]:
        """
        Analyze Locust stats CSV file.

        Returns:
            Analysis results dictionary
        """
        if not self.results_path.exists():
            raise FileNotFoundError(f"Results file not found: {self.results_path}")

        # Read CSV
        df = pd.read_csv(self.results_path)

        analysis = {
            "summary": self._compute_summary(df),
            "endpoints": self._analyze_endpoints(df),
            "performance_issues": self._detect_issues(df),
            "recommendations": []
        }

        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(analysis)

        return analysis

    def _compute_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Compute overall summary statistics."""

        # Filter to final timestamp for totals
        if 'Timestamp' in df.columns:
            final_df = df[df['Timestamp'] == df['Timestamp'].max()]
        else:
            final_df = df

        # Aggregate across all endpoints
        total_requests = final_df['Total Request Count'].sum() if 'Total Request Count' in final_df.columns else 0
        total_failures = final_df['Total Failure Count'].sum() if 'Total Failure Count' in final_df.columns else 0

        # Average response times weighted by request count
        if 'Average Response Time' in final_df.columns and total_requests > 0:
            avg_response = (
                (final_df['Average Response Time'] * final_df['Total Request Count']).sum() / total_requests
            )
        else:
            avg_response = 0

        # RPS
        total_rps = final_df['Requests/s'].sum() if 'Requests/s' in final_df.columns else 0

        return {
            "total_requests": int(total_requests),
            "total_failures": int(total_failures),
            "failure_rate": (total_failures / total_requests * 100) if total_requests > 0 else 0,
            "avg_response_time_ms": round(avg_response, 2),
            "total_rps": round(total_rps, 2)
        }

    def _analyze_endpoints(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Analyze performance by endpoint."""

        if 'Name' not in df.columns:
            return []

        # Get latest stats for each endpoint
        if 'Timestamp' in df.columns:
            df = df[df['Timestamp'] == df['Timestamp'].max()]

        endpoints = []

        for _, row in df.iterrows():
            name = row.get('Name', 'Unknown')
            if name in ['Aggregated', 'Total']:
                continue

            endpoint = {
                "name": name,
                "requests": int(row.get('Total Request Count', 0)),
                "failures": int(row.get('Total Failure Count', 0)),
                "avg_response_time": round(row.get('Average Response Time', 0), 2),
                "min_response_time": round(row.get('Min Response Time', 0), 2),
                "max_response_time": round(row.get('Max Response Time', 0), 2),
                "rps": round(row.get('Requests/s', 0), 2)
            }

            # Add percentiles if available
            if '50%' in row:
                endpoint["p50"] = round(row.get('50%', 0), 2)
            if '95%' in row:
                endpoint["p95"] = round(row.get('95%', 0), 2)
            if '99%' in row:
                endpoint["p99"] = round(row.get('99%', 0), 2)

            endpoints.append(endpoint)

        # Sort by request count descending
        endpoints.sort(key=lambda x: x['requests'], reverse=True)

        return endpoints

    def _detect_issues(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect performance issues."""

        issues = []

        if 'Name' not in df.columns:
            return issues

        # Get latest stats
        if 'Timestamp' in df.columns:
            df = df[df['Timestamp'] == df['Timestamp'].max()]

        for _, row in df.iterrows():
            name = row.get('Name', 'Unknown')
            if name in ['Aggregated', 'Total']:
                continue

            # Check high failure rate
            requests = row.get('Total Request Count', 0)
            failures = row.get('Total Failure Count', 0)
            if requests > 0:
                failure_rate = failures / requests * 100
                if failure_rate > 5:
                    issues.append({
                        "type": "high_failure_rate",
                        "endpoint": name,
                        "value": round(failure_rate, 2),
                        "severity": "critical" if failure_rate > 10 else "warning"
                    })

            # Check slow response times
            avg_response = row.get('Average Response Time', 0)
            if avg_response > 2000:
                issues.append({
                    "type": "slow_response",
                    "endpoint": name,
                    "value": round(avg_response, 2),
                    "severity": "critical" if avg_response > 5000 else "warning"
                })

            # Check P99 latency
            if '99%' in row:
                p99 = row.get('99%', 0)
                if p99 > 5000:
                    issues.append({
                        "type": "high_p99_latency",
                        "endpoint": name,
                        "value": round(p99, 2),
                        "severity": "warning"
                    })

        return issues

    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on analysis."""

        recommendations = []

        # Check overall failure rate
        failure_rate = analysis['summary']['failure_rate']
        if failure_rate > 5:
            recommendations.append(
                f"High failure rate ({failure_rate:.2f}%) detected. "
                "Investigate error logs and add error handling."
            )

        # Check response times
        avg_response = analysis['summary']['avg_response_time_ms']
        if avg_response > 1000:
            recommendations.append(
                f"Average response time ({avg_response:.2f}ms) exceeds target. "
                "Consider caching, database indexing, or query optimization."
            )

        # Check for specific slow endpoints
        slow_endpoints = [
            ep for ep in analysis['endpoints']
            if ep['avg_response_time'] > 2000
        ]
        if slow_endpoints:
            names = [ep['name'] for ep in slow_endpoints[:3]]
            recommendations.append(
                f"Slow endpoints detected: {', '.join(names)}. "
                "Profile these endpoints to identify bottlenecks."
            )

        # Check for high P99 latency
        high_p99_endpoints = [
            ep for ep in analysis['endpoints']
            if 'p99' in ep and ep['p99'] > 5000
        ]
        if high_p99_endpoints:
            recommendations.append(
                "High P99 latency detected. This indicates inconsistent performance. "
                "Look for resource contention or garbage collection issues."
            )

        if not recommendations:
            recommendations.append(
                "Performance looks good! All metrics within acceptable ranges."
            )

        return recommendations

    def generate_report(self, output_path: str = None) -> str:
        """
        Generate performance report.

        Args:
            output_path: Optional path to save report JSON

        Returns:
            Formatted report string
        """
        analysis = self.analyze_csv_stats()

        # Generate text report
        report = []
        report.append("=" * 70)
        report.append("PERFORMANCE ANALYSIS REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Source: {self.results_path}")
        report.append("")

        # Summary
        report.append("SUMMARY")
        report.append("-" * 70)
        summary = analysis['summary']
        report.append(f"Total Requests:        {summary['total_requests']:,}")
        report.append(f"Total Failures:        {summary['total_failures']:,}")
        report.append(f"Failure Rate:          {summary['failure_rate']:.2f}%")
        report.append(f"Avg Response Time:     {summary['avg_response_time_ms']:.2f}ms")
        report.append(f"Requests/Second:       {summary['total_rps']:.2f}")
        report.append("")

        # Top endpoints
        report.append("TOP ENDPOINTS")
        report.append("-" * 70)
        for ep in analysis['endpoints'][:10]:
            report.append(f"\n{ep['name']}")
            report.append(f"  Requests: {ep['requests']:,} | Failures: {ep['failures']}")
            report.append(f"  Avg: {ep['avg_response_time']:.2f}ms | Min: {ep['min_response_time']:.2f}ms | Max: {ep['max_response_time']:.2f}ms")
            if 'p95' in ep:
                report.append(f"  P50: {ep['p50']:.2f}ms | P95: {ep['p95']:.2f}ms | P99: {ep['p99']:.2f}ms")
        report.append("")

        # Issues
        if analysis['performance_issues']:
            report.append("PERFORMANCE ISSUES")
            report.append("-" * 70)
            for issue in analysis['performance_issues']:
                severity = issue['severity'].upper()
                report.append(f"[{severity}] {issue['type']}: {issue['endpoint']}")
                report.append(f"  Value: {issue['value']}")
            report.append("")

        # Recommendations
        report.append("RECOMMENDATIONS")
        report.append("-" * 70)
        for i, rec in enumerate(analysis['recommendations'], 1):
            report.append(f"{i}. {rec}")
        report.append("")

        report.append("=" * 70)

        report_text = "\n".join(report)

        # Save JSON analysis
        if output_path:
            output_path = Path(output_path)
            with open(output_path, 'w') as f:
                json.dump(analysis, f, indent=2)
            print(f"Analysis saved to: {output_path}")

        return report_text


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python analyze_results.py <stats_history.csv> [output.json]")
        print("\nExample:")
        print("  python analyze_results.py load_tests/reports/stats_history.csv analysis.json")
        sys.exit(1)

    results_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    analyzer = PerformanceAnalyzer(results_path)

    try:
        report = analyzer.generate_report(output_path)
        print(report)
    except Exception as e:
        print(f"Error analyzing results: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
