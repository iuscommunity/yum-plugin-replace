
Name: yum-plugin-replace        
Version:    0.2
Release:    1%{?dist}
Summary:    Package Replacement Plugin for Yum

Group:      System Environment/Base     
License:    GPL
URL:        http://github.com/derks/yum-plugin-replace
Source0:    http://dl.iuscommunity.org/pub/%{name}/%{name}-%{version}.tar.gz
BuildRoot:  %(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)

Requires:   yum  

%description
This plugin enables the ability to replace an installed package, with another
package that provides the same thing.  It was developed specifically for the
IUS Community Project whose packages have alternative names as to not
automatically upgrade stock packages.  They also do not Obsolete the packages
they provide, therefore making upgrading a little bit more tedious.  For
example upgrading 'mysql' to 'mysql50' or 'mysql51' requires first
uninstalling 'mysql' and then installing the alternate package name. 

%prep
%setup -q


%build
# pass

%install
rm -rf %{buildroot}
%{__mkdir} -p   %{buildroot}%{_sysconfdir}/yum/pluginconf.d/ \
                %{buildroot}%{_prefix}/lib/yum-plugins/

%{__install} -m 0644 ./etc/yum/pluginconf.d/replace.conf \
    %{buildroot}%{_sysconfdir}/yum/pluginconf.d/
%{__install} -m 0644 ./lib/yum-plugins/replace.py \
    %{buildroot}%{_prefix}/lib/yum-plugins/

%clean
rm -rf %{buildroot}


%files
%defattr(-,root,root,-)
%doc README LICENSE ChangeLog
%config(noreplace) %{_sysconfdir}/yum/pluginconf.d/replace.conf
%{_prefix}/lib/yum-plugins/replace.py*



%changelog
* Fri Jul 30 2010 BJ Dierkes <wdierkes@rackspace.com> - 0.2-1
- Latest sources

* Tue Jul 13 2010 BJ Dierkes <wdierkes@rackspace.com> - 0.1-1
- Initial spec build.

