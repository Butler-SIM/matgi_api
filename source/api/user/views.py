import math
from django.db import transaction
from django.db.models import Q
from datetime import datetime, timedelta, date

from django.db.models import Count

from django.shortcuts import get_object_or_404
from django.http import Http404

from rest_framework.permissions import AllowAny, IsAuthenticated
from dj_rest_auth.registration.views import RegisterView
from rest_framework.permissions import AllowAny

from common import create_coupon_number
from sf_coupon.models import CouponModel, CouponFormModel

from user.models import User, UserDeliveryInfo, UserPromotions
from user.serializers import (
    UserDeliveryInfoSerializer,
    UserSerializer,
    UserPromotionsOnlySerializer,
    UserInfoPutSerializer,
)

from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes

from with_buy.models import WithBuyOrder


class CustomRegisterView(RegisterView):
    @transaction.atomic()
    def create(self, request, *args, **kwargs):
        # 이메일 중복 확인
        if User.objects.filter(email=request.data["email"]).exists():
            return Response(
                {"data": request.data, "message": "already exist"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 마케팅 동의 확인
        elif request.data["marketing_check"] == None:
            return Response(
                {"data": request.data, "message": "marketing_check is null"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 비밀번호1 & 비밀번호2 동일 확인
        elif not request.data["password1"] == request.data["password2"]:
            return Response(
                {
                    "data": request.data,
                    "message": "password1 need to be same with password2",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        response = super().create(request, *args, **kwargs)

        custom_data = {
            "message": "done with registration",
        }
        request.data.update(custom_data)

        # 데이터베이스에 마케팅 동의, 이름, 연락처, 성별, 출생년도
        user = User.objects.get(email=request.data["email"])
        user.marketing_check = request.data["marketing_check"]
        user.name = request.data.get("name", None)
        user.phone_number = request.data.get("phone_number", None)
        user.gender = request.data.get("gender", None)
        user.birth_year = request.data.get("birth_year", None)
        user.birth_day = request.data.get("birth_day", None)
        user.nickname = "엔듀" + str(user.id)
        user.save()

        # 회원가입 축하 쿠폰 발급 (쿠폰 양식이 있으면)
        if CouponFormModel.objects.filter(issuance_type="join", is_used=True).exists():
            coupon_form = CouponFormModel.objects.filter(issuance_type="join", is_used=True)

            for coupon_obj in coupon_form:
                for i in range(coupon_obj.count):
                    create_coupon_number(coupon_obj, user)

        return Response(
            {
                "data": response.data,
            },
            status=status.HTTP_201_CREATED,
        )


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer

    def get_queryset(self):
        users = User.objects.all().order_by("-date_joined")
        if not users:
            raise Http404
        return users

    def get_users(self, request):
        """
        관리지 유저 리스트 조회
        """
        users = User.objects.all()
        auth = request.auth
        page = request.GET.get("page", None)
        sort = request.GET.get("sort", "recent")
        start_date = request.GET.get("start_date", None)
        end_date = request.GET.get("end_date", None)
        search = request.GET.get("search", None)
        group = request.GET.get("group", None)  # 관리자 쿠폰 발급 유저 필터링

        if group == "FILTER01":  # 회원 가입 후 구매 없는 고객

            user_list = [
                i.id
                for i in users
                if not i.withbuyorder_set.exclude(
                    Q(order_status="결제대기") | Q(order_status="주문취소")
                ).exists()
            ]

            list = UserSerializer(User.objects.filter(id__in=user_list), many=True).data
            return Response({"list": list})

        elif group == "FILTER02":  # 첫 구매 후 2주 이상 구매 없는 고객 리스트
            user = WithBuyOrder.objects.select_related("user").exclude(
                Q(order_status="결제대기") | Q(order_status="주문취소")
            )
            user_list = []
            for i in user:
                order_model = (
                    WithBuyOrder.objects.filter(user_id=i.user)
                    .exclude(Q(order_status="결제대기") | Q(order_status="주문취소"))
                    .order_by("-order_date")
                )

                if len(order_model) == 1:
                    last_order_date = order_model.first().order_date
                    two_weeks_plus_day = last_order_date + timedelta(days=15)

                    if two_weeks_plus_day < datetime.now():
                        user_list.append(order_model.first().user.id)

            list = UserSerializer(User.objects.filter(id__in=user_list), many=True).data

            return Response({"list": list})

        elif group == "FILTER03":  # 2회 이하 구매한 고객 리스트
            user = WithBuyOrder.objects.select_related("user").exclude(
                Q(order_status="결제대기") | Q(order_status="주문취소")
            )

            user_list = []
            for i in user:
                order_model = (
                    WithBuyOrder.objects.filter(user_id=i.user)
                    .exclude(Q(order_status="결제대기") | Q(order_status="주문취소"))
                    .order_by("-order_date")
                )

                if len(order_model) <= 2:
                    user_list.append(order_model.first().user.id)

            list = UserSerializer(User.objects.filter(id__in=user_list), many=True).data

            return Response({"list": list})

        elif group == "FILTER04":  # 3회 이상 구매한 고객 리스트
            user = WithBuyOrder.objects.select_related("user").exclude(
                Q(order_status="결제대기") | Q(order_status="주문취소")
            )

            user_list = []
            for i in user:
                order_model = (
                    WithBuyOrder.objects.filter(user_id=i.user)
                    .exclude(Q(order_status="결제대기") | Q(order_status="주문취소"))
                    .order_by("-order_date")
                )
                if len(order_model) >= 3:
                    user_list.append(order_model.first().user.id)

            list = UserSerializer(User.objects.filter(id__in=user_list), many=True).data

            return Response({"list": list})
        # 기간 설정
        if start_date:
            users = users.filter(
                date_joined__gte=datetime.strptime(str(start_date), "%Y-%m-%d")
            )

        if end_date:
            users = users.filter(
                date_joined__lt=datetime.strptime(str(end_date), "%Y-%m-%d")
                + timedelta(days=1)
            )
        if search:
            try:
                users = users.filter(id=search)
            except Exception as e:
                users = users.filter(Q(email__contains=search) | Q(name=search))

        # 솔팅
        sortby_mapping = {
            "recent": "-date_joined",
            "-recent": "date_joined",
        }
        users = (
            users.annotate(count_of_articles=Count("article")).order_by(
                "-count_of_articles"
            )
            if sort == "number"
            else users.order_by(sortby_mapping[sort])
        )

        if page is not None:
            # 페이지 네이션
            page = int(page)
            default_page_size = 10
            offset = (page - 1) * default_page_size
            limit = page * default_page_size
            users_count = users.count()
            users = users[offset:limit]
            # 전체 유저 수

            paging = {
                "total_page": math.ceil(users_count / default_page_size),
                "current_page": page,
                "total_sorted_items": users_count,
                "total_items": User.objects.all().count(),
            }
            list = UserSerializer(users, many=True, context={"request": request}).data
            return Response({"list": list, "paging": paging})

        if start_date is None:
            list = []
            for i in users:
                address = ""

                if UserDeliveryInfo.objects.filter(user_id=i.id, is_default=1).exists():
                    deliver_model = UserDeliveryInfo.objects.filter(
                        user_id=i.id, is_default=1
                    ).last()
                    address = f"{deliver_model.address1} {deliver_model.address2}"
                    delivery_type = deliver_model.delivery_type

                else:
                    address = ""
                    delivery_type = None

                list.append(
                    {
                        "id": i.id,
                        "marketing_check": i.marketing_check,
                        "date_joined": i.date_joined,
                        "email": i.email,
                        "name": i.name,
                        "phone_number": i.phone_number,
                        "gender": i.gender,
                        "main_delivery_info": {
                            "address": address,
                            "delivery_type": delivery_type,
                        },
                        "is_bag_deposit": i.is_bag_deposit,
                    }
                )
        else:
            user_obj = UserDeliveryInfo.objects.select_related("user").filter()
            list = []
            for i in User.objects.filter(
                date_joined__range=(
                    datetime.strptime(str(start_date), "%Y-%m-%d"),
                    datetime.strptime(str(end_date), "%Y-%m-%d") + timedelta(days=1),
                )
            ):

                address = ""

                if UserDeliveryInfo.objects.filter(user_id=i.id, is_default=1).exists():
                    deliver_model = UserDeliveryInfo.objects.filter(
                        user_id=i.id, is_default=1
                    ).last()
                    address = f"{deliver_model.address1} {deliver_model.address2}"
                    delivery_type = deliver_model.delivery_type

                else:
                    address = ""
                    delivery_type = None

                list.append(
                    {
                        "id": i.id,
                        "marketing_check": i.marketing_check,
                        "date_joined": i.date_joined,
                        "email": i.email,
                        "name": i.name,
                        "phone_number": i.phone_number,
                        "gender": i.gender,
                        "main_delivery_info": {
                            "address": address,
                            "delivery_type": delivery_type,
                        },
                        "is_bag_deposit": i.is_bag_deposit,
                    }
                )

        return Response({"list": list})

    def get_user_info(self, request):
        user = get_object_or_404(User, id=request.user.id)
        user_info = UserSerializer(user, context={"request": request}).data

        return Response(user_info)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = get_object_or_404(User, id=request.user.id)

        if request.data.get("user_status") == "3":
            request.data.update({"is_active": 0})

        serializer = UserInfoPutSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        self.perform_update(serializer)

        return Response({"result": "update success"})

    def users_delete(self, request):
        users = request.data.get("user")[0]
        user_model = User.objects.get(id=users)
        user_model.delete()
        return Response(
            {"message": "해당유저가 삭제되었습니다."}, status=status.HTTP_204_NO_CONTENT
        )

    def admin_check(self, request, email):
        admin = get_object_or_404(User, email=email)
        if not admin.is_superuser == True:
            return Response(
                {"message": "INVALID_ADMIN_EMAIL"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"message": "VALID_ADMIN_EMAIL"}, status=status.HTTP_200_OK)

    def admin_check_by_token(self, request):
        if request.user.is_superuser:
            return Response({"message": "VALID_ADMIN_TOKEN"}, status=200)
        else:
            return Response({"message": "INVALID_ADMIN_TOKEN"}, status=406)


class UserPasswordResetViewSet(viewsets.ModelViewSet):
    """
    url : user/password_reset
    비밀번호 변경 API
    method :[GET]
    description : 이메일 인증코드 검증 후 사용가능
    """

    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    def user_password_reset(self, request):
        user = get_object_or_404(User, email=request.data.get("email"))
        password1 = request.data.get("password1")
        password2 = request.data.get("password2")
        # 비밀번호1과 비밀번호2가 동일하지 않을 때
        if password2 != password1:
            return Response(
                {"message": "not matched"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        # 비밀번호 설정
        user.set_password(password1)
        user.save()
        return Response(
            {"message": "changed"},
            status=status.HTTP_200_OK,
        )


class UserDeliveryInfoViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = UserDeliveryInfo.objects.all()
    serializer_class = UserDeliveryInfoSerializer

    def get_delivery_infos(self, request, pk):
        user_delivery_infos = get_object_or_404(UserDeliveryInfo, id=pk)
        return Response(UserDeliveryInfoSerializer(user_delivery_infos).data)


class UserDeliveryInfoMeViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    queryset = UserDeliveryInfo.objects.all()
    serializer_class = UserDeliveryInfoSerializer

    def get_delivery_infos_me(self, request):
        user_delivery_infos = UserDeliveryInfo.objects.filter(user=request.user)
        return Response(
            self.serializer_class(user_delivery_infos, many=True).data
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def member_check(request, *args, **kwargs):
    """
    url : user/member_check?email=param
    이메일로 회원체크
    method :[GET]
    description : 이메일로 회원 체크
    """
    email = request.GET.get("email")

    if User.objects.filter(email=email).exists():

        return Response({"member": "True"})

    return Response({"member": "False"})


class UserPromotionsAPIView(generics.ListCreateAPIView):
    """
    url : user/user_promotion
    유저 프로모션
    method :[GET, POST]
    description : 유저 프로모션 참여내역 조회, 참여내역 생성
    """

    permission_classes = [AllowAny]
    queryset = UserPromotions.objects.all()
    serializer_class = UserPromotionsOnlySerializer

    def get(self, request):
        try:
            queryset = self.queryset.get(user=request.user)
            return Response(UserPromotionsOnlySerializer(queryset).data)

        except UserPromotions.DoesNotExist:
            return Response({"result": "프로모션 참여 내역 없음"})

    def post(self, request, *args, **kwargs):
        queryset = UserPromotions.objects.create(user=request.user, **request.data)

        try:
            result = [
                {"result": "success"},
                UserPromotionsOnlySerializer(queryset).data,
            ]

            return Response(result)

        except Exception:
            return Response({"result": "error"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_coupon(request, *args, **kwargs):
    """
    url : user/my_coupon
    나의 쿠폰 리스트 조회
    method :[GET]
    description :
    """

    my_coupon_list = CouponModel.objects.filter(
        user_id=request.user, is_used=False, end_date__gte=datetime.now()
    )

    return Response(my_coupon_list.values())
