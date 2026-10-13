import unittest

from gui_py import _crear_mascara_boton, _geometria_mascara_boton


class ButtonCornerMaskTests(unittest.TestCase):
    def test_geometry_matches_customtkinter_even_dimensions_and_clamps_radius(self) -> None:
        geometry = _geometria_mascara_boton(101.9, 9.5, 18.0)

        self.assertEqual(geometry, (101, 9, 100, 8, 4))

    def test_mask_has_no_pixels_outside_rounded_shape(self) -> None:
        mask = _crear_mascara_boton(101, 35, 100, 34, 10)

        self.assertEqual(mask.size, (101, 35))
        self.assertEqual(mask.getpixel((0, 0)), 0)
        self.assertEqual(mask.getpixel((100, 20)), 0)
        self.assertEqual(mask.getpixel((20, 34)), 0)
        self.assertEqual(mask.getpixel((50, 17)), 255)


if __name__ == "__main__":
    unittest.main()
