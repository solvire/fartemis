class JobSource:
    """Constants for job board sources"""
    LINKEDIN = 'linkedin'
    INDEED = 'indeed'
    GLASSDOOR = 'glassdoor'
    MONSTER = 'monster'
    WELLFOUND = 'wellfound'
    REMOTE_OK = 'remote_ok'
    WE_WORK_REMOTELY = 'we_work_remotely'
    GITHUB_JOBS = 'github_jobs'
    DIRECTLY_SOURCED = 'directly_sourced'
    OTHER = 'other'
    
    CHOICES = (
        (LINKEDIN, 'LinkedIn'),
        (INDEED, 'Indeed'),
        (GLASSDOOR, 'Glassdoor'),
        (MONSTER, 'Monster'),
        (WELLFOUND, 'WellFound'),
        (REMOTE_OK, 'RemoteOK'),
        (WE_WORK_REMOTELY, 'WeWorkRemotely'),
        (GITHUB_JOBS, 'GitHub Jobs'),
        (DIRECTLY_SOURCED, 'Directly Sourced'),
        (OTHER, 'Other'),
    )


class JobStatus:
    """Constants for job status"""
    NEW = 'new'
    BOOKMARKED = 'bookmarked'
    APPLIED = 'applied'
    INTERVIEW_SCHEDULED = 'interview_scheduled' 
    INTERVIEWED = 'interviewed'
    OFFER_RECEIVED = 'offer_received'
    REJECTED = 'rejected'
    DECLINED = 'declined'
    ACCEPTED = 'accepted'
    ARCHIVED = 'archived'
    
    CHOICES = (
        (NEW, 'New'),
        (BOOKMARKED, 'Bookmarked'),
        (APPLIED, 'Applied'),
        (INTERVIEW_SCHEDULED, 'Interview Scheduled'),
        (INTERVIEWED, 'Interviewed'),
        (OFFER_RECEIVED, 'Offer Received'),
        (REJECTED, 'Rejected'),
        (DECLINED, 'Declined'),
        (ACCEPTED, 'Accepted'),
        (ARCHIVED, 'Archived'),
    )


class JobLevel:
    """Constants for job seniority levels"""
    ENTRY = 'entry'
    ASSOCIATE = 'associate'
    MID = 'mid'
    SENIOR = 'senior'
    LEAD = 'lead'
    MANAGER = 'manager'
    DIRECTOR = 'director'
    VP = 'vp'
    EXECUTIVE = 'executive'
    
    CHOICES = (
        (ENTRY, 'Entry Level'),
        (ASSOCIATE, 'Associate'),
        (MID, 'Mid Level'),
        (SENIOR, 'Senior'),
        (LEAD, 'Lead'),
        (MANAGER, 'Manager'),
        (DIRECTOR, 'Director'),
        (VP, 'Vice President'),
        (EXECUTIVE, 'Executive'),
    )


class EmploymentType:
    """Constants for employment types"""
    FULL_TIME = 'full_time'
    PART_TIME = 'part_time'
    CONTRACT = 'contract'
    TEMPORARY = 'temporary'
    INTERNSHIP = 'internship'
    VOLUNTEER = 'volunteer'
    
    CHOICES = (
        (FULL_TIME, 'Full Time'),
        (PART_TIME, 'Part Time'),
        (CONTRACT, 'Contract'),
        (TEMPORARY, 'Temporary'),
        (INTERNSHIP, 'Internship'),
        (VOLUNTEER, 'Volunteer'),
    )

