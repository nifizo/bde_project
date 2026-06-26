from django.db.models import Q, Exists, OuterRef, When, IntegerField, FloatField, Count, ExpressionWrapper, Case, Value, F, Prefetch

from fame.models import Fame, FameLevels, FameUsers, ExpertiseAreas
from socialnetwork.models import Posts, SocialNetworkUsers


# general methods independent of html and REST views
# should be used by REST and html views


def _get_social_network_user(user) -> SocialNetworkUsers:
    """Given a FameUser, gets the social network user from the request. Assumes that the user is authenticated."""
    try:
        user = SocialNetworkUsers.objects.get(id=user.id)
    except SocialNetworkUsers.DoesNotExist:
        raise PermissionError("User does not exist")
    return user


def timeline(user: SocialNetworkUsers, start: int = 0, end: int = None, published=True, community_mode = False):
    """Get the timeline of the user. Assumes that the user is authenticated."""

    if community_mode:
        # T4
        # in community mode, posts of communities are displayed if ALL of the following criteria are met:
        # 1. the author of the post is a member of the community
        # 2. the user is a member of the community
        # 3. the post contains the community’s expertise area
        # 4. the post is published or the user is the author

        #all communities of user
        all_comms = user.communities.all()
        # Returns posts such that author is community member,
        # expertise areas of posts are user's communities
        # are published or written by current user
        # filter by newest and unique
        posts = Posts.objects.filter(
            expertise_area_and_truth_ratings__in=all_comms, author__communities=F("expertise_area_and_truth_ratings")
        ).filter(Q(published=published) | Q(author=user)).distinct().order_by("-submitted")

    else:
        # in standard mode, posts of followed users are displayed
        _follows = user.follows.all()
        posts = Posts.objects.filter(
            (Q(author__in=_follows) & Q(published=published)) | Q(author=user)
        ).order_by("-submitted")
    if end is None:
        return posts[start:]
    else:
        return posts[start:end+1]


def search(keyword: str, start: int = 0, end: int = None, published=True):
    """Search for all posts in the system containing the keyword. Assumes that all posts are public"""
    posts = Posts.objects.filter(
        Q(content__icontains=keyword)
        | Q(author__email__icontains=keyword)
        | Q(author__first_name__icontains=keyword)
        | Q(author__last_name__icontains=keyword),
        published=published,
    ).order_by("-submitted")
    if end is None:
        return posts[start:]
    else:
        return posts[start:end+1]


def follows(user: SocialNetworkUsers, start: int = 0, end: int = None):
    """Get the users followed by this user. Assumes that the user is authenticated."""
    _follows = user.follows.all()
    if end is None:
        return _follows[start:]
    else:
        return _follows[start:end+1]


def followers(user: SocialNetworkUsers, start: int = 0, end: int = None):
    """Get the followers of this user. Assumes that the user is authenticated."""
    _followers = user.followed_by.all()
    if end is None:
        return _followers[start:]
    else:
        return _followers[start:end+1]


def follow(user: SocialNetworkUsers, user_to_follow: SocialNetworkUsers):
    """Follow a user. Assumes that the user is authenticated. If user already follows the user, signal that."""
    if user_to_follow in user.follows.all():
        return {"followed": False}
    user.follows.add(user_to_follow)
    user.save()
    return {"followed": True}


def unfollow(user: SocialNetworkUsers, user_to_unfollow: SocialNetworkUsers):
    """Unfollow a user. Assumes that the user is authenticated. If user does not follow the user anyway, signal that."""
    if user_to_unfollow not in user.follows.all():
        return {"unfollowed": False}
    user.follows.remove(user_to_unfollow)
    user.save()
    return {"unfollowed": True}


def submit_post(
    user: SocialNetworkUsers,
    content: str,
    cites: Posts = None,
    replies_to: Posts = None,
):
    """Submit a post for publication. Assumes that the user is authenticated.
    returns a tuple of three elements:
    1. a dictionary with the keys "published" and "id" (the id of the post)
    2. a list of dictionaries containing the expertise areas and their truth ratings
    3. a boolean indicating whether the user was banned and logged out and should be redirected to the login page
    """

    # create post  instance:
    post = Posts.objects.create(
        content=content,
        author=user,
        cites=cites,
        replies_to=replies_to,
    )

    # classify the content into expertise areas:
    # only publish the post if none of the expertise areas contains bullshit:
    _at_least_one_expertise_area_contains_bullshit, _expertise_areas = (
        post.determine_expertise_areas_and_truth_ratings()
    )
    post.published = not _at_least_one_expertise_area_contains_bullshit

    redirect_to_logout = False


    #########################
    # T1: Do not publish posts whose expertise area is negatively marked
    # in the author's existing fame profile.

    # Loop through every expertise area that the magic AI assigned to this post.
    for area_info in _expertise_areas:
        area = area_info["expertise_area"]

        if Fame.objects.filter(
            user=user,  # Fame entry belongs to the post's author
            expertise_area=area,  # Fame entry is for this expertise area
            fame_level__numeric_value__lt=0,  # Fame value is negative (< 0)
        ).exists():
            # Do not publish the post if negative fame exists.
            post.published = False
            # Stop checking because one negative expertise area
            # is enough to block publication.
            break
    #########################
    # T2: Apply penalties for expertise areas with negative truth ratings.

    # Process every expertise area assigned to the post by the magic AI.
    for area_info in _expertise_areas:

        # Extract the expertise area and its associated truth rating.
        area = area_info["expertise_area"]
        truth_rating = area_info["truth_rating"]

        # Ignore this expertise area if:
        # 1. the AI could not determine a truth rating, or
        # 2. the truth rating is non-negative.
        # T2 penalties only apply to negative truth ratings.
        if truth_rating is None or truth_rating.numeric_value >= 0:
            continue

        ######T2b
        try:
            # Try to find an existing Fame entry for this user
            # in the current expertise area.
            fame_entry = Fame.objects.get(user=user,expertise_area=area)
        except Fame.DoesNotExist:
            # T2b:
            # The user has no fame profile in this expertise area yet.
            # Create a new Fame entry with the initial negative level "Confuser".
            confuser_level = FameLevels.objects.get(name="Confuser")
            Fame.objects.create(user=user, expertise_area=area, fame_level=confuser_level,)
            # The T2b case is fully handled, so move on to
            # the next expertise area.
            continue
        try:
            #### T2a
            # Lower the user's fame level by exactly one step.
            fame_entry.fame_level = fame_entry.fame_level.get_next_lower_fame_level()

            # Persist the updated fame level to the database.
            fame_entry.save()
            #### T4 last
            # Getting super pro level value
            super_pro_level = FameLevels.objects.get(name="Super Pro")
            # if user's fame lvel is less than super pro, we remove him from this community
            if fame_entry.fame_level.numeric_value < super_pro_level.numeric_value:
                user.communities.remove(area)
        except ValueError:
            ##### T2c

            # get_next_lower_fame_level() raises ValueError when
            # the user is already at the lowest possible fame level.
            # Ban the user and disable their account.
            user.is_active = False
            user.is_banned = True
            user.save()
            # Unpublish all posts previously made by this user.
            Posts.objects.filter(author=user).update(published=False)
            # Force the current request to log the user out.
            redirect_to_logout = True
            # Also ensure the current post is unpublished.
            post.published = False
            break
    post.save()

    return (
        {"published": post.published, "id": post.id},
        _expertise_areas,
        redirect_to_logout,
    )


def rate_post(
    user: SocialNetworkUsers, post: Posts, rating_type: str, rating_score: int
):
    """Rate a post. Assumes that the user is authenticated. If user already rated the post with the given rating_type,
    update that rating score."""
    user_rating = None
    try:
        user_rating = user.userratings_set.get(post=post, rating_type=rating_type)
    except user.userratings_set.model.DoesNotExist:
        pass

    if user == post.author:
        raise PermissionError(
            "User is the author of the post. You cannot rate your own post."
        )

    if user_rating is not None:
        # update the existing rating:
        user_rating.rating_score = rating_score
        user_rating.save()
        return {"rated": True, "type": "update"}
    else:
        # create a new rating:
        user.userratings_set.add(
            post,
            through_defaults={"rating_type": rating_type, "rating_score": rating_score},
        )
        user.save()
        return {"rated": True, "type": "new"}


def fame(user: SocialNetworkUsers):
    """Get the fame of a user. Assumes that the user is authenticated."""
    try:
        user = SocialNetworkUsers.objects.get(id=user.id)
    except SocialNetworkUsers.DoesNotExist:
        raise ValueError("User does not exist")

    return user, Fame.objects.filter(user=user)


def bullshitters():
    """Return a Python dictionary mapping each existing expertise area in the fame profiles to a list of the users
    having negative fame for that expertise area. Each list should contain Python dictionaries as entries with keys
    ``user'' (for the user) and ``fame_level_numeric'' (for the corresponding fame value), and should be ranked, i.e.,
    users with the lowest fame are shown first, in case there is a tie, within that tie sort by date_joined
    (most recent first). Note that expertise areas with no expert may be omitted.
    """
    # Dictionary that will map:
    # ExpertiseArea -> list of users with negative fame in that area.
    by_area = {}

    # Retrieve all Fame entries whose fame value is negative.
    # select_related loads the related objects in the same query
    # to avoid extra database lookups later.
    entries = Fame.objects.filter(
        fame_level__numeric_value__lt=0
    ).select_related("user", "expertise_area", "fame_level")

    # Process each negative Fame entry.
    for entry in entries:
        # Get the expertise area associated with this Fame entry.
        area = entry.expertise_area

        # If we have not seen this expertise area before,
        # create an empty list for it in the dictionary.
        if area not in by_area:
            by_area[area] = []
        # Add this user and their fame value to the list
        # belonging to the expertise area.
        by_area[area].append({
            "user": entry.user,
            "fame_level_numeric": entry.fame_level.numeric_value,
        })
    # Sort each expertise area's list according to the specification.
    for area in by_area:
        by_area[area].sort(
            key=lambda item: (
                # Primary key:
                # lower (more negative) fame values come first.
                item["fame_level_numeric"],
                # Secondary key:
                # newer users come first if the fame values are equal.
                # We negate the timestamp to reverse the order.
                -item["user"].date_joined.timestamp(),
            )
        )

    # Return the final dictionary:
    # {expertise_area -> list of bullshitters}
    return by_area
    #########################





def join_community(user: SocialNetworkUsers, community: ExpertiseAreas):
    """Join a specified community. Note that this method does not check whether the user is eligible for joining the
    community.
    """
    user.communities.add(community)



def leave_community(user: SocialNetworkUsers, community: ExpertiseAreas):
    """Leave a specified community."""
    user.communities.remove(community)



def similar_users(user: SocialNetworkUsers):
    """Compute the similarity of user with all other users. The method returns a QuerySet of FameUsers annotated
    with an additional field 'similarity'. Sort the result in descending order according to 'similarity', in case
    there is a tie, within that tie sort by date_joined (most recent first)"""

    # load all fame entries of the given user
    # each entry connects the user with one expertise area and one fame level 
    user_fame_entries = Fame.objects.filter(user = user)

    # create dict that stores the given user's fame values later
    user_fame_dict = {} # key: expertise_area_id, value: numeric_value of the fame level

    # loop over each entry in the created dict
    for fame_entry in user_fame_entries: 
        # use the foreign key relationship to get the needed data
        expertise_area_id = fame_entry.expertise_area_id
        numeric_value = fame_entry.fame_level.numeric_value

        user_fame_dict[expertise_area_id] = numeric_value

    # if the given user has no fame entries, similarity cannot be calculated
    # return an empty QuerySet because the Task expects a QuerySet as a result
    if not user_fame_dict:                          
        return SocialNetworkUsers.objects.none()

    # load all other users
    # exclude the given user 
    # prefetch_related loads all related Fame entries for these users efficiently
    # select_related("fame_level") additionally loads the FameLevel of each Fame entry
    # This avoids many small database queries inside a loop
    other_users = (
        SocialNetworkUsers.objects
        .exclude(id=user.id)
        .prefetch_related(
            Prefetch(
                "fame_set",
                queryset=Fame.objects.select_related("fame_level"),
            )
        )
    )

    # store calculated similarity scores temporarily in the dict
    similarity_scores  = {} # key: user_id, value: similarity_score

    # compare the given user with every other user.
    for other_user in other_users:
        matching_expertise_areas = 0    # counter 

        # loop over all fame entries of the other user.
        for fame_entry in other_user.fame_set.all():

            # Check whether the given user has fame in the same expertise area.
            # If yes, this returns the given user's numeric fame value.
            # If no, this returns None.
            user_numeric_value = user_fame_dict.get(fame_entry.expertise_area_id)

            # if the given user does not have this expertise area, we ignore it
            if user_numeric_value is None:
                continue

            # calculate the absolute difference between both numeric fame values.
            difference = abs(
                user_numeric_value - fame_entry.fame_level.numeric_value
            )

            # if the difference is at most 100, this expertise area counts as similar.
            if difference <= 100:
                matching_expertise_areas += 1
        # End fame entries loop

        # users with zero matching expertise areas have similarity score 0.
        # the task says we should only return users with non-zero similarity.
        if matching_expertise_areas == 0:
            continue

        # calculate similarity as similarity = matching expertise areas / number of expertise areas of the given user.
        similarity = matching_expertise_areas / len(user_fame_dict)
        similarity_scores[other_user.id] = similarity
    # End other users loop
    
    # convert the Python-calculated scores into a Django annotation.
    # logic behind CASE: WHEN id = user_id THEN corresponding score.
    similarity_annotation = Case(
        *[
            When(id=user_id, then=Value(score))
            for user_id, score in similarity_scores.items()
        ],
        output_field=FloatField(),
    )

    # Return a QuerySet of users with the additional field "similarity".
    # Only users with a calculated similarity score are included.
    # Sorting:
    # 1. highest similarity first
    # 2. if equal, newest user first
    return (
        SocialNetworkUsers.objects
        .filter(id__in=similarity_scores.keys())
        .annotate(similarity=similarity_annotation)
        .order_by("-similarity", "-date_joined")
    )
    
