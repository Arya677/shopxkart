from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from carts.views import _cart_id
from carts.models import CartItem
from store.forms import ReviewFrom
from store.models import Product, ProductGallery, ReviewRating
from orders.models import OrderProduct
from category.models import Category
from django.db.models import Q
from django.core.paginator import Paginator



def store(request, category_slug=None): # Define a function to handle the store
    categories = None
    products =None

    if category_slug != None: # If the category_slug is not None
        categories = get_object_or_404(Category, slug=category_slug)
        products = Product.objects.filter(category = categories, is_available=True)
        paginator = Paginator(products, 6) # Show 6 products per page
        page = request.GET.get('page') # Get the current page number
        paged_products = paginator.get_page(page)
        product_count = products.count()
    else:
        products = Product.objects.all().filter(is_available=True).order_by('id') # Get all products
        paginator = Paginator(products, 6) # Show 6 products per page
        page = request.GET.get('page') # Get the current page number
        paged_products = paginator.get_page(page) # Get the products for the current page
        product_count = products.count() # Get the total number of products

    context = {
        'products': paged_products, # Pass the products to the template
        'product_count': product_count, # Pass the product count to the template
    } 
    return render(request,'store.html',context) # Return the render request

def product_detail(request, category_slug, product_slug):
    try:
        single_product = Product.objects.get(category__slug=category_slug, slug=product_slug)
        in_cart = CartItem.objects.filter(cart__cart_id=_cart_id(request), product=single_product).exists()
    except Exception as e:
        raise e

    orderproduct = False
    if request.user.is_authenticated:
        orderproduct = OrderProduct.objects.filter(user=request.user, product=single_product).exists()

    reviews = ReviewRating.objects.filter(product_id=single_product.id, status=True)

    # get the product gallery
    product_gallery = ProductGallery.objects.filter(product_id=single_product.id)


    context = { 
        'single_product': single_product,
        'in_cart': in_cart,
        'orderproduct': orderproduct,  
        'reviews': reviews,
        'product_gallery': product_gallery,
    }        
    return render(request, 'product_detail.html', context)

def search(request):
    keyword = request.GET.get('keyword')
    if keyword:
        products = Product.objects.order_by('-created_date').filter(Q(description__icontains=keyword) | Q(product_name__icontains=keyword))
        product_count = products.count()
    else:
        products = Product.objects.none()
        product_count = 0
    context = {
        'products': products,
        'product_count': product_count,
    }
    return render(request, 'store.html', context)

def submit_review(request, product_id):
    url = request.META.get('HTTP_REFERER')
    if request.method == 'POST':
        try:
            reviews = ReviewRating.objects.get(user__id=request.user.id, product__id=product_id)
            form = ReviewFrom(request.POST, instance=reviews)
            form.save()
            messages.success(request, 'Thank you! Your review has been updated.')
            return redirect(url)
        except ReviewRating.DoesNotExist:
            form = ReviewFrom(request.POST)
            if form.is_valid():
                data = ReviewRating()
                data.subject = form.cleaned_data['subject']
                data.rating = form.cleaned_data['rating']
                data.review = form.cleaned_data['review']
                data.ip = request.META.get('REMOTE_ADDR')
                data.product_id = product_id
                data.user_id = request.user.id
                data.save()
                messages.success(request, 'Thank you! Your review has been submitted.')
                return redirect(url)       
