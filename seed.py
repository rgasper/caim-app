import csv
import json
import os
import urllib.request
from random import choice, choices, randint

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from faker import Faker

from caim_base.models.animals import (Animal, AnimalImage, AnimalType, Breed,
                                      ZipCode)
from caim_base.models.awg import Awg
from caim_base.models.fosterer import FostererProfile

fake = Faker()

User = get_user_model()


def load_zips():
    ZipCode.objects.all().delete()
    file_name = "seed_data/zips.txt"
    with open(file_name) as csv_file:
        zips = []
        csv_reader = csv.reader(csv_file, delimiter=",")

        for row in csv_reader:
            p = ZipCode(
                zip_code=row[0],
                geo_location=Point(float(row[2]), float(row[1])),
            )
            zips.append(p)

        ZipCode.objects.bulk_create(zips)


def load_breeds(animal_type, file_name):
    f = open(file_name)
    breeds = json.load(f)

    with transaction.atomic():
        for handle in breeds:
            name = breeds[handle]
            b = Breed(name=name, slug=handle, animal_type=animal_type.upper())
            b.save()

    f.close()


def map_age(str):
    if str == "baby":
        return Animal.AnimalAge.BABY
    if str == "young":
        return Animal.AnimalAge.YOUNG
    if str == "adult":
        return Animal.AnimalAge.ADULT
    if str == "senior":
        return Animal.AnimalAge.SENIOR


def map_size(str):
    if str == "small":
        return Animal.AnimalSize.S
    if str == "medium":
        return Animal.AnimalSize.M
    if str == "large":
        return Animal.AnimalSize.L
    return None


def map_behavour(v):
    if v == True:
        return Animal.AnimalBehaviourGrade.GOOD
    if v == False:
        return Animal.AnimalBehaviourGrade.POOR
    return Animal.AnimalBehaviourGrade.NOT_TESTED


def map_sex(v):
    v = v.lower()
    if v == "female":
        return Animal.AnimalSex.F
    if v == "male":
        return Animal.AnimalSex.M
    return None


def lookup_breed(pfbreed):
    return Breed.objects.filter(slug=pfbreed["slug"]).first()


def upsert_awg(name, pf_id, city, state, zip, lat, lng):
    awg = Awg.objects.filter(petfinder_id=pf_id).first()
    if not awg:
        awg = Awg(
            name=name,
            petfinder_id=pf_id,
            city=city,
            state=state,
            zip_code=zip,
            geo_location=Point(lng, lat),
            status=Awg.AwgStatus.PUBLISHED,
        )
        awg.save()

    return awg


def load_animals(animal_type, file_name):
    f = open(file_name)
    animals = json.load(f)

    for hash_id in animals:
        try:
            a = animals[hash_id]
            aa = a["animal"]
            pf_id = aa["id"]
            print(a)
            print(aa)

            primary_breed = None
            secondary_breed = None
            if "primary_breed" in aa and aa["primary_breed"]:
                primary_breed = lookup_breed(aa["primary_breed"])
            if "secondary_breed" in aa and aa["secondary_breed"]:
                secondary_breed = lookup_breed(aa["primary_breed"])

            aorg = a["organization"]
            awg_pf_id = aorg["display_id"]

            awg = upsert_awg(
                aorg["name"],
                awg_pf_id,
                a["location"]["address"]["city"],
                a["location"]["address"]["state"],
                a["location"]["address"]["postal_code"],
                float(a["location"]["geo"]["latitude"]),
                float(a["location"]["geo"]["longitude"]),
            )

            print(aa)
            a = Animal(
                name=aa["name"],
                animal_type=AnimalType.DOG,
                primary_breed=primary_breed,
                secondary_breed=secondary_breed,
                petfinder_id=pf_id,
                is_published=True,
                awg_id=awg.id,
                is_mixed_breed=aa["is_mixed_breed"],
                is_unknown_breed=aa.get("is_unknown_breed", False),
                sex=map_sex(aa["sex"]),
                size=map_size(aa["size"].lower()),
                age=map_age(aa["age"].lower()),
                special_needs=aa.get("special_needs_notes", "") or "",
                description=aa.get("description", "") or "",
                is_special_needs=False,
                is_euth_listed=False,
                euth_date=fake.date_between(start_date="today", end_date="+30d"),
                is_spayed_neutered="Spay/Neuter" in aa["attributes"],
                is_vaccinations_current="Shots Current" in aa["attributes"],
                behaviour_dogs=map_behavour(aa["home_environment_attributes"].get("good_with_dogs", False)),
                behaviour_kids=map_behavour(aa["home_environment_attributes"].get("good_with_children", False)),
                behaviour_cats=map_behavour(aa["home_environment_attributes"].get("good_with_cats", False)),
            )
            image_url = aa["primary_photo_url"]
            img_result = urllib.request.urlretrieve(image_url)
            a.primary_photo.save(os.path.basename(image_url), File(open(img_result[0], "rb")))
            a.save()

            if aa["photo_urls"]:
                for image_url in aa["photo_urls"]:
                    print(image_url)
                    if image_url != aa["primary_photo_url"]:
                        ai = AnimalImage(animal=a)
                        img_result = urllib.request.urlretrieve(image_url)
                        ai.photo.save(os.path.basename(image_url), File(open(img_result[0], "rb")))
                        ai.save()
        except Exception as er:
            print(er)
            print("SKIPPEd")


def load_fosterers(num_desired_fosterers: int):
    print("loading fake fosterers...")
    fosterers = []
    for _ in range(num_desired_fosterers):
        # going through the fields in the same order they appear in the model
        user = User()
        user.username = fake.user_name()
        user.email = fake.email()
        user.save()
        fosterer = FostererProfile()
        fosterer.user = user
        fosterer.firstname = fake.first_name()
        fosterer.lastname = fake.last_name()
        fosterer.email = user.email
        fosterer.phone = fake.phone_number()
        try:
            fosterer.full_clean()
        except ValidationError as exc:
            phone_broke = exc.error_dict.get("phone", None)
            if phone_broke:
                fosterer.phone = None
            # lots of other fields are likely invalid here, don't raise
        fosterer.street_address = fake.address()
        fosterer.city = fake.city()[: FostererProfile.city.field.max_length - 1]
        fosterer.state = fake.state_abbr()
        fosterer.zip_code = fake.zipcode()
        # pick a random selections from these ChoiceArrayFields, from 1-max number of selections
        k = randint(1, len(fosterer.TypeOfAnimals.choices))
        fosterer.type_of_animals = list(set(choices([choice[0] for choice in fosterer.TypeOfAnimals.choices], k=k)))
        k = randint(1, len(fosterer.CategoryOfAnimals.choices))
        fosterer.category_of_animals = list(
            set(choices([choice[0] for choice in fosterer.CategoryOfAnimals.choices], k=k))
        )
        k = randint(1, len(fosterer.BehaviouralAttributes.choices))
        fosterer.behavioural_attributes = list(
            set(choices([choice[0] for choice in fosterer.BehaviouralAttributes.choices], k=k))
        )
        fosterer.timeframe = choice([choice[0] for choice in fosterer.Timeframe.choices])
        if fosterer.Timeframe.OTHER in fosterer.timeframe:
            fosterer.timeframe_other = fake.text(randint(5, 500))
        fosterer.num_existing_pets = randint(0, 10)
        fosterer.existing_pets_details = fake.text(randint(5, 500))
        fosterer.experience_description = fake.text(randint(5, 500))
        # pick a random selections from these choice fields, from 1-max number of selections
        k = randint(1, len(fosterer.ExperienceCategories.choices))
        fosterer.experience_categories = list(
            set(choices([choice[0] for choice in fosterer.ExperienceCategories.choices], k=k))
        )
        fosterer.experience_given_up_pet = fake.text(randint(5, 500))
        fosterer.reference_1 = fake.name()
        fosterer.reference_2 = fake.name()
        fosterer.reference_3 = fake.name()
        fosterer.people_at_home = fake.text(randint(5, 50))
        # from just normal choice fields, pick 1 choice
        fosterer.yard_type = choice([choice[0] for choice in fosterer.YardTypes.choices])
        fosterer.yard_fence_over_5ft = choice([choice[0] for choice in fosterer.YesNo.choices])
        fosterer.rent_own = choice([choice[0] for choice in fosterer.RentOwn.choices])
        if fosterer.rent_own == fosterer.RentOwn.RENT:
            fosterer.rent_restrictions = fake.text(randint(5, 50))
            fosterer.rent_ok_foster_pets = choice([choice[0] for choice in fosterer.YesNo.choices])
        else:
            fosterer.rent_restrictions = None
            fosterer.rent_ok_foster_pets = fosterer.YesNo.YES  # field not allowing null???
        fosterer.hours_alone_description = fake.text(10)
        fosterer.hours_alone_location = fake.text(10)
        fosterer.sleep_location = fake.text(10)
        fosterer.other_info = fake.text(50)
        fosterer.ever_been_convicted_abuse = choice([choice[0] for choice in fosterer.YesNo.choices])
        fosterer.agree_share_details = choice([choice[0] for choice in fosterer.YesNo.choices])
        fosterer.is_complete = choice([True, False])
        fosterer.full_clean()
        fosterers.append(fosterer)
    FostererProfile.objects.bulk_create(fosterers)


# Animal.objects.all().delete()
# Awg.objects.all().delete()
# Breed.objects.all().delete()

# load_zips()
# load_breeds("dog", "seed_data/dog-breeds.json")
# load_breeds("cat", "seed_data/cat-breeds.json")

# load_animals("dog", "seed_data/dogs.json")
# load_animals("dog", "seed_data/dogs2.json")
# load_animals("dog", "seed_data/dogs3.json")
load_fosterers(50)
