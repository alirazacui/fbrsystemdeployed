import os

# 1. Update pos/serializer.py
with open("pos/serializer.py", "a") as f:
    f.write("\n\nclass HSCodeSerializer(serializers.ModelSerializer):\n")
    f.write("    class Meta:\n")
    f.write("        model = HSCode\n")
    f.write("        fields = ['id', 'code', 'description', 'default_rate', 'uom']\n")

# 2. Update pos/views.py
with open("pos/views.py", "a") as f:
    f.write("\n\nfrom rest_framework import viewsets, filters, permissions\n")
    f.write("from rest_framework.pagination import PageNumberPagination\n")
    f.write("class StandardResultsSetPagination(PageNumberPagination):\n")
    f.write("    page_size = 50\n")
    f.write("    page_size_query_param = 'page_size'\n")
    f.write("    max_page_size = 1000\n")
    f.write("class HSCodeViewSet(viewsets.ReadOnlyModelViewSet):\n")
    f.write("    queryset = HSCode.objects.all()\n")
    f.write("    serializer_class = HSCodeSerializer\n")
    f.write("    permission_classes = [permissions.IsAuthenticated]\n")
    f.write("    filter_backends = [filters.SearchFilter]\n")
    f.write("    search_fields = ['code', 'description']\n")
    f.write("    pagination_class = StandardResultsSetPagination\n")

# 3. Update pos/urls.py
urls_content = open("pos/urls.py").read()
if "HSCodeViewSet" not in urls_content:
    urls_content = urls_content.replace(
        'router.register(r"debit-notes", DebitNoteViewSet, basename="debit-note")',
        'router.register(r"debit-notes", DebitNoteViewSet, basename="debit-note")\nrouter.register(r"hs-codes", HSCodeViewSet, basename="hs-code")'
    )
    with open("pos/urls.py", "w") as f:
        f.write(urls_content)

print("Appended successfully.")
