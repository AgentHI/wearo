from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from statistics import median
from typing import Literal, cast

from PIL import Image, ImageFilter, ImageOps


@dataclass(frozen=True)
class SplitJewelleryReference:
    necklace_image: bytes
    earring_image: bytes


JewelleryReferenceStrategy = Literal[
    "person_necklace",
    "person_earring",
    "person_necklace_earring",
    "person_combined_product",
]


@dataclass(frozen=True)
class RunwareJewelleryReferencePlan:
    images: tuple[bytes, ...]
    strategy: JewelleryReferenceStrategy


@dataclass(frozen=True)
class _ForegroundComponent:
    area: int
    box: tuple[int, int, int, int]
    pixels: tuple[int, ...]


def split_lower_earring_reference(image_bytes: bytes) -> SplitJewelleryReference | None:
    """Separate a catalogue necklace set into necklace-only and one-earring references.

    This intentionally handles the common catalogue layout where a necklace is displayed above
    one or two detached earrings on a simple background. It returns ``None`` when that layout
    cannot be identified confidently, allowing callers to keep the original reference.
    """

    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if image.width < 128 or image.height < 128:
        return None

    analysis = image.copy()
    analysis.thumbnail((384, 384), Image.Resampling.LANCZOS)
    background = _background_colour(analysis)
    components = _foreground_components(analysis, background)
    earrings = _earring_components(components, analysis.width, analysis.height)
    if not earrings:
        return None
    return _split_reference_images(image, analysis, components[0], earrings)


def plan_runware_jewellery_references(
    person: bytes, product: bytes
) -> RunwareJewelleryReferencePlan:
    """Classify a jewellery catalogue image and prepare unambiguous model references."""

    try:
        with Image.open(BytesIO(product)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, ValueError):
        return RunwareJewelleryReferencePlan(
            images=(person, product), strategy="person_combined_product"
        )
    if image.width < 128 or image.height < 128:
        return RunwareJewelleryReferencePlan(
            images=(person, product), strategy="person_combined_product"
        )

    analysis = image.copy()
    analysis.thumbnail((384, 384), Image.Resampling.LANCZOS)
    background = _background_colour(analysis)
    components = _foreground_components(analysis, background)
    if not components:
        return RunwareJewelleryReferencePlan(
            images=(person, product), strategy="person_combined_product"
        )

    largest = components[0]
    earrings = _earring_components(components, analysis.width, analysis.height)
    if _is_necklace_component(
        largest,
        analysis.width,
        analysis.height,
        has_detached_earrings=bool(earrings),
    ):
        if not earrings:
            return RunwareJewelleryReferencePlan(
                images=(person, product), strategy="person_necklace"
            )
        split = _split_reference_images(image, analysis, largest, earrings)
        return RunwareJewelleryReferencePlan(
            images=(person, split.necklace_image, split.earring_image),
            strategy="person_necklace_earring",
        )

    earring = _isolated_component_reference(image, analysis, largest)
    return RunwareJewelleryReferencePlan(
        images=(person, earring), strategy="person_earring"
    )


def runware_jewellery_reference_images(person: bytes, product: bytes) -> list[bytes]:
    """Compatibility wrapper for callers that need only the ordered images."""

    return list(plan_runware_jewellery_references(person, product).images)


def _is_necklace_component(
    component: _ForegroundComponent,
    width: int,
    height: int,
    *,
    has_detached_earrings: bool,
) -> bool:
    component_width = component.box[2] - component.box[0]
    component_height = component.box[3] - component.box[1]
    return (
        component_width >= width * 0.58
        and component_height >= height * 0.18
        and (
            has_detached_earrings
            or component_width >= component_height * 0.72
        )
    )


def _split_reference_images(
    image: Image.Image,
    analysis: Image.Image,
    necklace: _ForegroundComponent,
    earrings: list[_ForegroundComponent],
) -> SplitJewelleryReference:
    original_background = _background_colour(image)
    background_image = Image.new("RGB", image.size, original_background)
    necklace_mask = _component_mask([necklace], analysis.size, image.size)
    necklace_image = Image.composite(image, background_image, necklace_mask)
    exemplar = _single_earring_component(earrings[0], analysis.width)
    earring = _isolated_component_reference(image, analysis, exemplar)
    return SplitJewelleryReference(
        necklace_image=_jpeg(necklace_image),
        earring_image=earring,
    )


def _single_earring_component(
    component: _ForegroundComponent, analysis_width: int
) -> _ForegroundComponent:
    """Split a side-by-side earring pair joined by shadows into one exemplar."""

    left, top, right, bottom = component.box
    component_width = right - left
    component_height = bottom - top
    if component_width < component_height * 0.7:
        return component

    counts = [0] * component_width
    for index in component.pixels:
        _y, x = divmod(index, analysis_width)
        counts[x - left] += 1
    search_start = round(component_width * 0.3)
    search_end = round(component_width * 0.7)
    if search_end <= search_start:
        return component
    split_offset = min(range(search_start, search_end), key=counts.__getitem__)
    left_peak = max(counts[:split_offset], default=0)
    right_peak = max(counts[split_offset + 1 :], default=0)
    if counts[split_offset] > min(left_peak, right_peak) * 0.5:
        return component

    pixels = tuple(
        index
        for index in component.pixels
        if index % analysis_width <= left + split_offset
    )
    if not pixels:
        return component
    xs = [index % analysis_width for index in pixels]
    ys = [index // analysis_width for index in pixels]
    return _ForegroundComponent(
        area=len(pixels),
        box=(min(xs), min(ys), max(xs) + 1, max(ys) + 1),
        pixels=pixels,
    )


def _isolated_component_reference(
    image: Image.Image,
    analysis: Image.Image,
    component: _ForegroundComponent,
) -> bytes:
    background = _background_colour(image)
    background_image = Image.new("RGB", image.size, background)
    component_mask = _component_mask([component], analysis.size, image.size)
    isolated = Image.composite(image, background_image, component_mask)
    box = _scale_and_pad_box(
        component.box,
        image.width / analysis.width,
        image.height / analysis.height,
        image.width,
        image.height,
    )
    return _jpeg(_centre_on_square(isolated.crop(box), background))


def _background_colour(image: Image.Image) -> tuple[int, int, int]:
    inset_x = max(1, image.width // 40)
    inset_y = max(1, image.height // 40)
    radius = max(1, min(image.width, image.height) // 80)
    samples: list[tuple[int, int, int]] = []
    for centre_x, centre_y in (
        (inset_x, inset_y),
        (image.width - inset_x - 1, inset_y),
        (inset_x, image.height - inset_y - 1),
        (image.width - inset_x - 1, image.height - inset_y - 1),
    ):
        for y in range(max(0, centre_y - radius), min(image.height, centre_y + radius + 1)):
            for x in range(max(0, centre_x - radius), min(image.width, centre_x + radius + 1)):
                samples.append(cast(tuple[int, int, int], image.getpixel((x, y))))
    channels = [int(median(channel)) for channel in zip(*samples, strict=True)]
    return channels[0], channels[1], channels[2]


def _foreground_components(
    image: Image.Image, background: tuple[int, int, int]
) -> list[_ForegroundComponent]:
    mask_image = Image.new("L", image.size)
    mask_pixels = mask_image.load()
    if mask_pixels is None:
        raise RuntimeError("Unable to access jewellery reference pixels")
    for y in range(image.height):
        for x in range(image.width):
            pixel = cast(tuple[int, int, int], image.getpixel((x, y)))
            difference = max(abs(pixel[channel] - background[channel]) for channel in range(3))
            if difference >= 60:
                mask_pixels[x, y] = 255
    mask_image = mask_image.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(3))
    mask = bytearray(
        1 if mask_image.getpixel((x, y)) else 0
        for y in range(image.height)
        for x in range(image.width)
    )
    visited = bytearray(len(mask))
    components: list[_ForegroundComponent] = []
    minimum_area = max(12, round(image.width * image.height * 0.0005))
    for start, foreground in enumerate(mask):
        if not foreground or visited[start]:
            continue
        visited[start] = 1
        stack = [start]
        area = 0
        component_pixels: list[int] = []
        left = right = start % image.width
        top = bottom = start // image.width
        while stack:
            index = stack.pop()
            y, x = divmod(index, image.width)
            area += 1
            component_pixels.append(index)
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for neighbour_y in range(max(0, y - 1), min(image.height, y + 2)):
                for neighbour_x in range(max(0, x - 1), min(image.width, x + 2)):
                    neighbour = neighbour_y * image.width + neighbour_x
                    if mask[neighbour] and not visited[neighbour]:
                        visited[neighbour] = 1
                        stack.append(neighbour)
        if area >= minimum_area:
            components.append(
                _ForegroundComponent(
                    area=area,
                    box=(left, top, right + 1, bottom + 1),
                    pixels=tuple(component_pixels),
                )
            )
    components.sort(key=lambda component: component.area, reverse=True)
    return components


def _earring_components(
    components: list[_ForegroundComponent], width: int, height: int
) -> list[_ForegroundComponent]:
    if len(components) < 2:
        return []
    necklace = components[0]
    candidates = [
        component
        for component in components[1:]
        if component.area >= necklace.area * 0.025
        and component.box[2] - component.box[0] < width * 0.45
        and component.box[3] - component.box[1] < height * 0.5
        and 0.18
        <= (component.box[2] - component.box[0])
        / (component.box[3] - component.box[1])
        <= 2.5
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda component: component.area, reverse=True)
    largest = candidates[0]
    matching = [
        component
        for component in candidates
        if component.area >= largest.area * 0.45
        and component.area <= largest.area * 2.2
    ][:2]
    matching.sort(key=lambda component: component.box[0])
    return matching


def _component_mask(
    components: list[_ForegroundComponent],
    analysis_size: tuple[int, int],
    output_size: tuple[int, int],
) -> Image.Image:
    width, _height = analysis_size
    mask = Image.new("L", analysis_size)
    pixels = mask.load()
    if pixels is None:
        raise RuntimeError("Unable to create jewellery component mask")
    for component in components:
        for index in component.pixels:
            y, x = divmod(index, width)
            pixels[x, y] = 255
    mask = mask.filter(ImageFilter.MaxFilter(3))
    return mask.resize(output_size, Image.Resampling.NEAREST)


def _scale_and_pad_box(
    box: tuple[int, int, int, int],
    scale_x: float,
    scale_y: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    scaled = (
        round(left * scale_x),
        round(top * scale_y),
        round(right * scale_x),
        round(bottom * scale_y),
    )
    padding = max(8, round(max(scaled[2] - scaled[0], scaled[3] - scaled[1]) * 0.08))
    return (
        max(0, scaled[0] - padding),
        max(0, scaled[1] - padding),
        min(image_width, scaled[2] + padding),
        min(image_height, scaled[3] + padding),
    )


def _centre_on_square(image: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    side = max(image.width, image.height)
    margin = max(16, round(side * 0.28))
    canvas = Image.new("RGB", (side + margin * 2, side + margin * 2), background)
    canvas.paste(image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2))
    canvas.thumbnail((768, 768), Image.Resampling.LANCZOS)
    return canvas


def _jpeg(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, "JPEG", quality=96, optimize=True)
    return output.getvalue()
