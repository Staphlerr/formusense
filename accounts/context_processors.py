from accounts.access import has_consumer_access, has_research_access


def roles(request):
    return {
        "can_consumer": has_consumer_access(request.user),
        "can_research": has_research_access(request.user),
    }
