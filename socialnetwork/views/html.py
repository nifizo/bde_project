from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from socialnetwork import api
from socialnetwork.api import _get_social_network_user
from socialnetwork.models import SocialNetworkUsers
from socialnetwork.serializers import PostsSerializer

from fame.models import ExpertiseAreas, FameLevels, Fame


@require_http_methods(["GET"])
@login_required
def timeline(request):
    # using the serializer to get the data, then use JSON in the template!
    # avoids having to do the same thing twice

    # initialize community mode to False the first time in the session
    if 'community_mode' not in request.session:
        request.session['community_mode'] = False

    community_mode = request.session["community_mode"]
    user = _get_social_network_user(request.user)
    joined_communities = user.communities.all()
    super_pro = FameLevels.objects.get(name="Super Pro")
    eligible_expertise_area_ids = Fame.objects.filter(
        user=user,
        fame_level__numeric_value__gte=super_pro.numeric_value,
    ).values_list(
        "expertise_area_id", flat=True,
    )
    available_communities = ExpertiseAreas.objects.filter(
        id__in=eligible_expertise_area_ids,
    ).exclude(
        id__in=joined_communities.values_list("id", flat=True),
    )
    # get extra URL parameters:
    keyword = request.GET.get("search", "")
    published = request.GET.get("published", True)
    error = request.GET.get("error", None)

    # if keyword is not empty, use search method of API:
    if keyword and keyword != "":
        context = {
            "posts": PostsSerializer(
                api.search(keyword, published=published), many=True
            ).data,
            "searchkeyword": keyword,
            "error": error,
            "followers": list(api.follows(_get_social_network_user(request.user)).values_list('id', flat=True)),
            "community_mode": community_mode,
            "joined_communities": joined_communities,
            "available_communities": available_communities,
        }
    else:  # otherwise, use timeline method of API:

        context = {
            "posts": PostsSerializer(
                api.timeline(
                    _get_social_network_user(request.user),
                    published=published,
                    community_mode=community_mode,
                ),
                many=True,
            ).data,
            "searchkeyword": "",
            "error": error,
            "followers": list(api.follows(_get_social_network_user(request.user)).values_list('id', flat=True)),
            "community_mode": community_mode,
            "joined_communities": joined_communities,
            "available_communities": available_communities,
        }

    return render(request, "timeline.html", context=context)


@require_http_methods(["POST"])
@login_required
def follow(request):
    user = _get_social_network_user(request.user)
    user_to_follow = SocialNetworkUsers.objects.get(id=request.POST.get("user_id"))
    api.follow(user, user_to_follow)
    return redirect(reverse("sn:timeline"))


@require_http_methods(["POST"])
@login_required
def unfollow(request):
    user = _get_social_network_user(request.user)
    user_to_unfollow = SocialNetworkUsers.objects.get(id=request.POST.get("user_id"))
    api.unfollow(user, user_to_unfollow)
    return redirect(reverse("sn:timeline"))


@require_http_methods(["GET"])
@login_required
def bullshitters(request):
    user = _get_social_network_user(request.user)
    bullshitters = api.bullshitters()
    context = {
        "bullshitters": bullshitters,
    }
    return render(request, "bullshitters.html", context = context)

@require_http_methods(["POST"])
@login_required
def toggle_community_mode(request):
    current_mode = request.session.get("community_mode", False)
    request.session["community_mode"] = not current_mode
    return redirect(reverse("sn:timeline"))

@require_http_methods(["POST"])
@login_required
def join_community(request):
    user = _get_social_network_user(request.user)
    expertise_area_id = request.POST.get("expertise_area_id")
    expertise_area = get_object_or_404(
        ExpertiseAreas,
        id=expertise_area_id,
    )
    api.join_community(user, expertise_area)
    return redirect(reverse("sn:timeline"))

@require_http_methods(["POST"])
@login_required
def leave_community(request):
    user = _get_social_network_user(request.user)
    expertise_area_id = request.POST.get("expertise_area_id")
    expertise_area = get_object_or_404(
        ExpertiseAreas,
        id=expertise_area_id,
    )
    api.leave_community(user, expertise_area)
    return redirect(reverse("sn:timeline"))

@require_http_methods(["GET"])
@login_required
def similar_users(request):

    # Convert Django's built-in User object (request.user)
    # into the corresponding SocialNetworkUser object.
    # We need this because the API works with SocialNetworkUser objects.
    user = _get_social_network_user(request.user)

    # Call the API function that calculates all similar users.
    # The result is usually a QuerySet containing all users
    # together with their calculated similarity score.
    similar_users_result = api.similar_users(user)

    # Create a context dictionary.
    # Everything inside this dictionary will be available
    # inside the HTML template.
    context = {
        "similar_users": similar_users_result,
    }

    # Render the HTML template "similar_users.html"
    # and pass the context dictionary to it.
    # Django replaces all template variables with the values
    # from the context before sending the finished HTML page back to the browser.
    return render(request, "similar_users.html", context = context)