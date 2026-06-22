from django.urls import path

from socialnetwork.views.html import timeline, leave_community, join_community, toggle_community_mode
from socialnetwork.views.html import follow
from socialnetwork.views.html import unfollow
from socialnetwork.views.rest import PostsListApiView
from socialnetwork.views.html import similar_users
from socialnetwork.views.html import bullshitters

app_name = "socialnetwork"

urlpatterns = [
    path("html/community/leave_community", leave_community, name="leave_community"),
    path("html/community/join_community", join_community, name="join_community"),
    path("html/community/toggle", toggle_community_mode, name="toggle_community_mode"),
    path("html/bullshitters", bullshitters, name="bullshitters"),
    path("api/posts", PostsListApiView.as_view(), name="posts_fulllist"),
    path("html/timeline", timeline, name="timeline"),
    path("api/follow", follow, name="follow"),
    path("api/unfollow", unfollow, name="unfollow"),
    path("html/similar-users", similar_users, name="similar_users")
]
