import asyncio
import flet as ft

class GalleryShimmer(ft.Column):
    def __init__(self, is_dark: bool):
        super().__init__(tight=True, key="gallery_shimmer_skeleton")
        self.is_dark = is_dark
        # Use the colors! 
        self.base_color = ft.Colors.GREY_900 if is_dark else ft.Colors.GREY_300
        self.highlight_color = ft.Colors.GREY_800 if is_dark else ft.Colors.GREY_200
        
        # Build the internal UI
        self.controls = [
            ft.Container(
                content=ft.Row(
                    [self._make_shimmer_item() for _ in range(3)],
                    spacing=20,
                    scroll=ft.ScrollMode.HIDDEN,
                ),
                padding=ft.Padding.only(bottom=10),
            ),
            # Chip Placeholder
            ft.Container(
                width=180, height=40, 
                bgcolor=self.base_color, 
                border_radius=20,
                animate_opacity=ft.Animation(800, "easeInOut")
            ),
        ]

    def _make_shimmer_item(self):
        """Creates a single card + caption skeleton."""
        return ft.Column([
            ft.Card(
                content=ft.Container(
                    width=220, height=300,
                    bgcolor=self.base_color,
                    border_radius=8,
                    # We'll animate the bgcolor itself for a 'shimmer' feel
                    animate=ft.Animation(800, "easeInOut"),
                ),
                elevation=4,
            ),
            ft.Container(
                height=20, width=150,
                bgcolor=self.base_color,
                border_radius=4,
                margin=ft.Margin.only(bottom=60),
                animate=ft.Animation(800, "easeInOut"),
            )
        ], tight=True)

    async def animate_shimmer(self):
        """The loop that handles the pulsing effect."""
        while self.page:
            # Toggle between base and highlight
            new_color = self.highlight_color if self.controls[1].bgcolor == self.base_color else self.base_color
            
            # Update the chip placeholder
            self.controls[1].bgcolor = new_color
            
            # Update the cards and caption bars
            # Row -> controls (list of items) -> Column -> Card/Container
            for item_column in self.controls[0].content.controls:
                item_column.controls[0].content.bgcolor = new_color # The Card Image
                item_column.controls[1].bgcolor = new_color         # The Caption bar
            
            self.update()
            await asyncio.sleep(0.8)