from rest_framework import serializers


class DateRangeReportQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    branch = serializers.IntegerField(required=False, allow_null=True)
    cashier = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        if data['date_from'] > data['date_to']:
            raise serializers.ValidationError('date_from no puede ser posterior a date_to.')
        return data


class SalesByProductQuerySerializer(DateRangeReportQuerySerializer):
    group_by = serializers.ChoiceField(choices=['product', 'category', 'cashier'], required=False, default='product')


class BranchOnlyReportQuerySerializer(serializers.Serializer):
    branch = serializers.IntegerField(required=False, allow_null=True)


class NearExpiryReportQuerySerializer(serializers.Serializer):
    branch = serializers.IntegerField(required=False, allow_null=True)
    days = serializers.IntegerField(required=False, default=7, min_value=1, max_value=365)


class ShiftDetailReportQuerySerializer(serializers.Serializer):
    shift = serializers.IntegerField()
