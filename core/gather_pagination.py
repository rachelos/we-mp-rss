DEFAULT_CATCH_UP_MAX_PAGES = 10
HARD_CATCH_UP_MAX_PAGES = 20


def normalize_catch_up_max_pages(value) -> int:
    try:
        pages = int(value)
    except (TypeError, ValueError):
        pages = DEFAULT_CATCH_UP_MAX_PAGES

    return min(max(pages, 1), HARD_CATCH_UP_MAX_PAGES)


def should_stop_after_page(callback_results, stop_on_existing: bool) -> bool:
    if not stop_on_existing:
        return False
    return any(result is False for result in callback_results)
