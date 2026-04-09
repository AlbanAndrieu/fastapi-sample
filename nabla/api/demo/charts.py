from datetime import datetime
from typing import Dict, List

import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

from nabla.utils.logger import logger


class ChartFactory:
    def __init__(self):
        logger.info("Initializing ChartFactory")

        # Define consistent color scheme
        self.colors = {
            "temperature": "#3B82F6",  # Blue
            "humidity": "#10B981",  # Green
            "pressure": "#8B5CF6",  # Purple
            "normal": "#10B981",  # Green
            "warning": "#F59E0B",  # Yellow
            "critical": "#EF4444",  # Red
        }

        # Common layout settings (transparent canvas; text/grid tuned for #000 page bg — matches /api)
        self._font_stack = "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,sans-serif"
        self.layout_defaults = {
            "plot_bgcolor": "rgba(0,0,0,0)",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "margin": {"l": 20, "r": 20, "t": 40, "b": 20},
            "font": {"family": self._font_stack, "size": 12, "color": "#cccccc"},
            "legend": {
                "font": {"color": "#a3a3a3", "family": self._font_stack},
                "bgcolor": "rgba(17,17,17,0.92)",
                "bordercolor": "#333333",
                "borderwidth": 1,
            },
        }
        self._axis_line = "#333333"
        self._grid_line = "#333333"
        self._tick_color = "#888888"
        self._title_color = "#aaaaaa"

    def create_time_series_chart(self, df: pl.DataFrame) -> str:
        # "timestamp": datetime.now().isoformat(),
        # "temperature": round(random.uniform(self.min_temp, self.max_temp), 1),  # nosec
        # "humidity": round(random.uniform(self.min_humidity, self.max_humidity), 1),  # nosec
        # "pressure": round(random.uniform(1000, 1030), 1),  # nosec
        # "status": random.choice(["normal", "warning", "critical"]),  # nosec

        # Create subplot with secondary y-axis
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("Temperature & Humidity", "Atmospheric Pressure"),
            specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
        )

        # Convert Polars to lists for Plotly (efficient extraction)
        timestamps = df["timestamp"].to_list()
        temperatures = df["temperature"].to_list()
        humidity = df["humidity"].to_list()
        pressure = df["pressure"].to_list()

        logger.debug(
            f"Data extracted: {len(timestamps)} timestamps, temp range: {min(temperatures):.1f}-{max(temperatures):.1f}°C",
        )

        # Temperature line (primary y-axis)
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=temperatures,
                name="Temperature (°C)",
                line={"color": self.colors["temperature"], "width": 2},
                hovertemplate="<b>Temperature</b><br>%{y:.1f}°C<br>%{x}<extra></extra>",
            ),
            row=1,
            col=1,
        )

        # Humidity line (secondary y-axis)
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=humidity,
                name="Humidity (%)",
                line={"color": self.colors["humidity"], "width": 2},
                yaxis="y2",
                hovertemplate="<b>Humidity</b><br>%{y:.1f}%<br>%{x}<extra></extra>",
            ),
            row=1,
            col=1,
        )

        # Pressure line
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=pressure,
                name="Pressure (hPa)",
                line={"color": self.colors["pressure"], "width": 2},
                hovertemplate="<b>Pressure</b><br>%{y:.1f} hPa<br>%{x}<extra></extra>",
            ),
            row=2,
            col=1,
        )

        # Update layout
        fig.update_layout(
            **self.layout_defaults,
            # height=500,
            showlegend=True,
            hovermode="x unified",
        )

        axis_common = {
            "showgrid": True,
            "gridcolor": self._grid_line,
            "zerolinecolor": self._axis_line,
            "linecolor": self._axis_line,
            "tickfont": {"color": self._tick_color},
            "title": {"font": {"color": self._title_color}},
        }
        fig.update_yaxes(**axis_common)
        fig.update_xaxes(**axis_common)

        # Update y-axes
        fig.update_yaxes(title_text="Temperature (°C)", row=1, col=1)
        fig.update_yaxes(title_text="Humidity (%)", secondary_y=True, row=1, col=1)
        fig.update_yaxes(title_text="Pressure (hPa)", row=2, col=1)
        fig.update_xaxes(title_text="Time", row=2, col=1)

        fig.update_annotations(
            font={
                "color": "#ffffff",
                "family": self._font_stack,
                "size": 13,
            },
        )

        logger.info("Time series chart created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="timeseries-chart")

    def create_status_distribution(self, df: pl.DataFrame) -> str:
        """Create status distribution pie chart"""
        if df.is_empty():
            logger.warning("Cannot create status chart: empty DataFrame")
            return self._create_empty_chart("No status data")

        # Get status counts using Polars
        status_counts = df["status"].value_counts().sort("status")

        logger.debug(
            f"Status distribution: {dict(zip(status_counts['status'].to_list(), status_counts['count'].to_list(), strict=False))}",
        )

        fig = go.Figure(
            data=[
                go.Pie(
                    labels=status_counts["status"].to_list(),
                    values=status_counts["count"].to_list(),
                    marker_colors=[self.colors.get(status, "#6B7280") for status in status_counts["status"].to_list()],
                    hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>",
                    textinfo="label+percent",
                ),
            ],
        )

        fig.update_layout(
            **self.layout_defaults,
            title={
                "text": "Sensor Status Distribution",
                "font": {"family": self._font_stack, "size": 14, "color": "#ffffff"},
            },
            # height=300
        )
        fig.update_yaxes(showgrid=False, zeroline=False)
        fig.update_xaxes(showgrid=False, zeroline=False)

        logger.info("Status distribution chart created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="status-chart")

    def create_correlation_heatmap(self, df: pl.DataFrame) -> str:
        """Create correlation heatmap between metrics"""
        if df.is_empty() or len(df) < 2:
            logger.warning("Cannot create correlation heatmap: insufficient data")
            return self._create_empty_chart("Insufficient data for correlation")

        logger.debug("Calculating correlation matrix")

        # Calculate correlation matrix using Polars
        numeric_cols = ["temperature", "humidity", "pressure"]
        corr_data = []

        for col1 in numeric_cols:
            row = []
            for col2 in numeric_cols:
                if col1 == col2:
                    correlation = 1.0
                else:
                    # Calculate Pearson correlation
                    correlation = df.select(pl.corr(col1, col2)).item()
                    if correlation is None:  # Handle NaN correlations
                        correlation = 0.0
                row.append(correlation)
            corr_data.append(row)

        logger.debug(f"Correlation matrix calculated: {corr_data}")

        fig = go.Figure(
            data=go.Heatmap(
                z=corr_data,
                x=numeric_cols,
                y=numeric_cols,
                colorscale="RdBu",
                zmid=0,
                text=[[f"{val:.2f}" for val in row] for row in corr_data],
                texttemplate="%{text}",
                textfont={"size": 12},
                hovertemplate="<b>%{y} vs %{x}</b><br>Correlation: %{z:.3f}<extra></extra>",
            ),
        )

        fig.update_layout(
            **self.layout_defaults,
            title={
                "text": "Sensor Correlation Matrix",
                "font": {"family": self._font_stack, "size": 14, "color": "#ffffff"},
            },
            # height=300
        )
        axis_common = {
            "showgrid": False,
            "linecolor": self._axis_line,
            "tickfont": {"color": self._tick_color},
            "title": {"font": {"color": self._title_color}},
        }
        fig.update_xaxes(**axis_common)
        fig.update_yaxes(**axis_common)

        logger.info("Correlation heatmap created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="correlation-chart")

    def create_anomaly_highlights(self, df: pl.DataFrame, anomalies: List[Dict]) -> str:
        """Create chart highlighting anomalous readings"""
        if df.is_empty():
            logger.warning("Cannot create anomaly chart: empty DataFrame")
            return self._create_empty_chart("No data for anomaly detection")

        logger.debug(f"Creating anomaly chart with {len(anomalies)} anomalies")

        timestamps = df["timestamp"].to_list()
        temperatures = df["temperature"].to_list()

        fig = go.Figure()

        # Normal temperature line
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=temperatures,
                mode="lines+markers",
                name="Temperature",
                line={"color": self.colors["temperature"]},
                marker={"size": 4},
            ),
        )

        # Highlight anomalies
        if anomalies:
            anomaly_times = [datetime.fromisoformat(a["timestamp"]) for a in anomalies]
            anomaly_temps = [a["temperature"] for a in anomalies]

            logger.info(f"Highlighting {len(anomalies)} anomalies on chart")

            fig.add_trace(
                go.Scatter(
                    x=anomaly_times,
                    y=anomaly_temps,
                    mode="markers",
                    name="Anomalies",
                    marker={
                        "color": self.colors["critical"],
                        "size": 10,
                        "symbol": "diamond",
                    },
                    hovertemplate="<b>Anomaly Detected</b><br>Temperature: %{y:.1f}°C<br>%{x}<extra></extra>",
                ),
            )

        fig.update_layout(
            **self.layout_defaults,
            title={
                "text": "Temperature with Anomaly Detection",
                "font": {"family": self._font_stack, "size": 14, "color": "#ffffff"},
            },
            xaxis_title="Time",
            yaxis_title="Temperature (°C)",
        )
        axis_common = {
            "showgrid": True,
            "gridcolor": self._grid_line,
            "zerolinecolor": self._axis_line,
            "linecolor": self._axis_line,
            "tickfont": {"color": self._tick_color},
            "title": {"font": {"color": self._title_color}},
        }
        fig.update_xaxes(**axis_common)
        fig.update_yaxes(**axis_common)

        logger.info("Anomaly detection chart created successfully")
        return fig.to_html(include_plotlyjs="cdn", div_id="anomaly-chart")

    def _create_empty_chart(self, message: str) -> str:
        """Create placeholder chart for empty data"""
        logger.debug(f"Creating empty chart placeholder: {message}")

        fig = go.Figure()
        fig.add_annotation(
            text=message,
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            xanchor="center",
            yanchor="middle",
            font={"size": 16, "color": "#888888", "family": self._font_stack},
        )
        fig.update_layout(
            **self.layout_defaults,
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return fig.to_html(include_plotlyjs="cdn")
