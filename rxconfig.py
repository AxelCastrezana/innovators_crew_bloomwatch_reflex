import reflex as rx

config = rx.Config(
    app_name="innovators_crew_bloomwatch_reflex",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)